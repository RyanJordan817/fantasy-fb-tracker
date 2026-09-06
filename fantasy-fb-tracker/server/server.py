import os
from espn_api.football import League
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, origins=['http://localhost:5173', 'http://localhost:5174'])

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
                        breakdown = week_data['projected_breakdown']

                        if isinstance(breakdown, dict):
                            stats_bd["proj_rec"] = round(float(breakdown.get('receivingReceptions', 0)),2)
                            stats_bd["proj_rec_yards"] = round(float(breakdown.get('receivingYards', 0)),2)
                            stats_bd["proj_rush"] = round(float(breakdown.get('rushingYards', 0)),2)
                        else:
                            stats_bd["proj_rec"] = 0.0
                            stats_bd["proj_rush"] = 0.0
                    else:
                        stats_bd["proj_rec"] = 0.0
                        stats_bd["proj_rush"] = 0.0

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