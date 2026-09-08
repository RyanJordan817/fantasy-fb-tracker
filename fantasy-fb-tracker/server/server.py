import os
from espn_api.football import League
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from ml_service import NFLPlayerProjector
import logging

load_dotenv()

app = Flask(__name__)
CORS(app, origins=['http://localhost:5173', 'http://localhost:5174'])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ml_projector = NFLPlayerProjector()

try:
    ml_projector.load_models()
    logger.info("Loading existing ML models")
except:
    logger.info("Training new ML models...")

    ml_projector.train_models(seasons=[2019, 2020, 2021, 2022, 2023])
    ml_projector.save_models()
    logger.info("ML models trained and saved")

try: 
    league_id = int(os.getenv('LEAGUE_ID'))
    year = int(os.getenv('YEAR'))
    espn_s2 = os.getenv('ESPN_S2')
    swid = os.getenv('SWID')

    if not all([league_id, year, espn_s2, swid]):
        raise ValueError("Missing required environment variables")
    
    league = League(
        league_id=int(league_id),
        year=year,
        espn_s2=espn_s2,
        swid=swid
    )
    print("league initialized successfully")

except Exception as e:
    print(f"Error initializing league: {e}")
    league = None

# Player Predictions
@app.route('/predict/player', methods=['POST'])
def predict_player():
    """
    Predict fantasy points for a specific player
    Request body: {"player_name": "Patrick Mahomes", "position": "QB", "team": "KC"}
    """
    try:
        data = request.json
        player_name = data.get('player_name')
        pos = data.get('position')
        team = data.get('team', '')

        if not player_name or not pos:
            return jsonify({"error": "player_name and position are required"}), 400

        player_info = None
        for team_obj in league.teams:
            for player in team_obj.roster:
                if player.name.lower() == player_name.lower():
                    player_info = {
                        'name': player.name,
                        'position': pos,
                        'team': team
                    }
                    break
                if player_info:
                    break

            if not player_info:
                return jsonify({"error": "Player not found"}), 404

            prediction = ml_projector.predict_player(
                player_info['name'],
                player_info['position'],
                player_info['team']
            )

            return jsonify({
                "player": player_info['name'],
                "position": player_info['position'],
                "predicted_points": prediction,
                "confidence": "medium"
            })

    except Exception as e:
        logger.error(f"Error predicting player: {e}")
        return jsonify({"error": str(e)}), 500

# Fetch cirrent standings
@app.route('/standings', methods=['GET'])
def get_standings():
    try:
        standings = league.standings()
        standings_data = []
        for team in standings:
            standings_data.append({
                "team_id": team.team_id,
                "team_name": team.team_name,
                "team_abbrev": team.team_abbrev,
                "wins": team.wins,
                "losses": team.losses,
                "ties": team.ties,
                "points_for": team.points_for,
                "points_against": team.points_against,
                "waiver_rank": team.waiver_rank,
                "acquisitions": team.acquisitions,
                "drops": team.drops,
                "trades": team.trades,
                "owners": team.owners, # array of owners (though one for my league)
                "stats": team.stats,
                "streak_type": team.streak_type,
                "streak_length": team.streak_length,
                "standing": team.standing,
                "final_standing": team.final_standing,
                "draft_projected_rank": team.draft_projected_rank,
                "playoff_pct": team.playoff_pct
            })
        return jsonify(standings_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# view current week's mathcups
@app.route('/matchups', methods=['GET'])
def get_matchups():
    try:
        matchups = league.box_scores()
        matchup_data = []
        for match in matchups:
            matchup_data.append({
                "home_team": match.home_team.team_name,
                "home_score": match.home_score,
                "home_prodj": match.home_projected,
                "away_team": match.away_team.team_name,
                "away_score": match.away_score,
                "away_prodj": match.away_projected,
                "is_playoff": match.is_playoff,
                "match_type": match.matchup_type
            })
        return jsonify(matchup_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Look at specific team roster
@app.route('/team/<int:team_id>/roster', methods=['GET'])
def get_team_roster(team_id):
    try:
        team = next((team for team in league.teams if team.team_id == team_id), None)
        if not team:
            return jsonify(f"No team found for id {team_id}"), 404

        print(f"team:\n {team.roster}")
        curr_week = getattr(league, 'current_week', 1)
        players = team.roster
        roster = []
        for player in players:
            stats_dict = {}
            stats_bd ={}
            if hasattr(player, 'stats') and isinstance(player.stats, dict):
                week_data = player.stats.get(curr_week)
                if not week_data:
                    week_data = player.stats.get(1)

                if week_data:
                    if 'projected_points' in week_data:
                        stats_dict["proj_pts"] = round(float(week_data['projected_points']),2)
                    else:
                        stats_dict["proj_pts"] = 0.0
                    
                    if 'points' in week_data:
                        stats_dict["act_pts"] = round(float(week_data['points']),2)
                    else:
                        stats_dict["act_pts"] = 0.0

                    if 'projected_breakdown' in week_data and week_data['projected_breakdown']:
                        proj_breakdown = week_data['projected_breakdown']

                        if isinstance(proj_breakdown, dict):
                            stats_bd["proj_rec"] = round(float(proj_breakdown.get('receivingReceptions', 0)),2)
                            stats_bd["proj_rec_yards"] = round(float(proj_breakdown.get('receivingYards', 0)),2)
                            stats_bd["proj_rush"] = round(float(proj_breakdown.get('rushingYards', 0)),2)
                            stats_bd["proj_rec_td"] = round(float(proj_breakdown.get('receivingTouchdowns', 0)),2)
                            stats_bd["proj_rush_td"] = round(float(proj_breakdown.get('rushingTouchdowns', 0)),2)
                            stats_bd["proj_pass"] = round(float(proj_breakdown.get('passingYards', 0)),2)
                            stats_bd["proj_pass_td"] = round(float(proj_breakdown.get('passingTouchdowns', 0)),2)
                        else:
                            stats_bd["proj_rec"] = 0.0
                            stats_bd["proj_rec_yards"] = 0.0
                            stats_bd["proj_rush"] = 0.0
                            stats_bd["proj_pass"] = 0.0
                            stats_bd["proj_pass_td"] = 0.0
                    else:
                        stats_bd["proj_rec"] = 0.0
                        stats_bd["proj_rec_yards"] = 0.0
                        stats_bd["proj_rush"] = 0.0
                        stats_bd["proj_pass"] = 0.0
                        stats_bd["proj_pass_td"] = 0.0

            roster.append({
                "name": player.name,
                "id": player.playerId,
                "pos_rank": player.posRank,
                "pro_team": player.proTeam,
                "lineup_pos": player.lineupSlot,
                "acquisition_type": player.acquisitionType,
                "position": player.position,
                "injury_status": player.injuryStatus,
                "is_injured": player.injured,
                "total_points": player.total_points,
                "avg_points": player.avg_points,
                "prodj_total_pts": player.projected_total_points,
                "prodj_avg_pts": player.projected_avg_points,
                "percent_owned": player.percent_owned,
                "percent_start": player.percent_started,
                "stats": stats_dict,
                "breakdown": stats_bd,
                "week": curr_week
        })
        return jsonify(roster)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/teams', methods=['GET'])
def get_team():
    try:
        teams = league.teams
        team_list = []
        for team in teams:
            team_list.append({
                "name": team.team_name,
                "team_id": team.team_id
            })
        return jsonify(team_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5000, debug=True)