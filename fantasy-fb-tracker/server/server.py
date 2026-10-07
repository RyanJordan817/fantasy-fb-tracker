import os
import json
import tempfile
from threading import RLock
from typing import Any
from espn_api.football import League
from espn_api.football.player import Player
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

year = None
league = None
try:
    league_id = int(os.environ['LEAGUE_ID'])
    year = int(os.environ['YEAR'])
    espn_s2 = os.getenv('ESPN_S2')
    swid = os.getenv('SWID')

    if not all([espn_s2, swid]):
        raise ValueError("Missing required environment variables")

    league = League(
        league_id=league_id,
        year=year,
        espn_s2=espn_s2,
        swid=swid
    )
    logger.info("ESPN league initialized successfully")
except Exception:
    logger.exception("Error initializing ESPN league")

ml_projector = None
if league is not None:
    scoring_format = getattr(league.settings, 'scoring_format', None)
    if not isinstance(scoring_format, list) or not scoring_format:
        raise ValueError("ESPN league did not provide usable scoring settings")
    ml_projector = NFLPlayerProjector(scoring_format)
    model_path = os.path.join(os.path.dirname(__file__), '..', 'models')
    try:
        ml_projector.load_models(model_path)
        logger.info("Loaded existing ML models")
    except (FileNotFoundError, ValueError) as error:
        logger.info("Training ML models because saved models are unavailable or stale: %s", error)
    if (
        ml_projector.training_season != league.year
        or ml_projector.training_through_week is None
        or ml_projector.training_through_week < league.current_week - 1
    ):
        logger.info("Refreshing ML models with completed weeks from season %s", league.year)
        ml_projector.train_models(
            seasons=range(max(2019, league.year - 6), league.year + 1),
            holdout_season=league.year - 1,
            current_season=league.year,
            through_week=league.current_week,
        )
        ml_projector.save_models(model_path)

weekly_data_lock = RLock()
WeeklyDataCache = dict[str, Any]
weekly_data_cache: WeeklyDataCache | None = None
weekly_data_cache_loaded = False
WEEKLY_DATA_CACHE_VERSION = 2


def _weekly_data_path(season: int):
    return os.path.join(
        os.path.dirname(__file__),
        'data',
        f'espn_weekly_scores_{season}.json',
    )


def _load_weekly_data_cache(season: int) -> WeeklyDataCache:
    global weekly_data_cache, weekly_data_cache_loaded

    if weekly_data_cache_loaded and weekly_data_cache is not None:
        return weekly_data_cache

    weekly_data_cache_loaded = True
    path = _weekly_data_path(season)
    try:
        with open(path, encoding='utf-8') as cache_file:
            stored = json.load(cache_file)
        if (
            stored.get('season') == season
            and stored.get('schema_version') == WEEKLY_DATA_CACHE_VERSION
        ):
            weekly_data_cache = {
                'season': season,
                'fetched_weeks': set(stored.get('fetched_weeks', [])),
                'players': stored.get('players', {}),
            }
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError, AttributeError, TypeError) as error:
        logger.warning("Unable to load ESPN weekly score cache %s: %s", path, error)

    if weekly_data_cache is None:
        weekly_data_cache = {
            'season': season,
            'fetched_weeks': set(),
            'players': {},
        }
    return weekly_data_cache


def _save_weekly_data_cache(cache: WeeklyDataCache):
    path = _weekly_data_path(cache['season'])
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=directory,
            delete=False,
        ) as cache_file:
            temporary_path = cache_file.name
            json.dump({
                'season': cache['season'],
                'schema_version': WEEKLY_DATA_CACHE_VERSION,
                'fetched_weeks': sorted(cache['fetched_weeks']),
                'players': cache['players'],
            }, cache_file)
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise


def _fetch_espn_weekly_data(league_instance: League, week: int):
    data = league_instance.espn_request.league_get(params={
        'view': 'mRoster',
        'scoringPeriodId': week,
    })
    players_for_week = {}
    for team_data in data.get('teams', []):
        roster = team_data.get('roster', {})
        for entry in roster.get('entries', []):
            player = Player(entry, league_instance.year)
            stats = player.stats.get(week, {})
            players_for_week[str(player.playerId)] = {
                'name': player.name,
                'position': player.position,
                'pro_team': player.proTeam,
                'actual': stats.get('points'),
                'espn_projection': stats.get('projected_points'),
            }
    return players_for_week


def _player_opponent(player, week: int):
    schedule = getattr(player, 'schedule', None)
    if not isinstance(schedule, dict):
        return None
    matchup = schedule.get(str(week), {})
    if isinstance(matchup, dict):
        return matchup.get('team')
    return None


def _capture_current_week_ml_snapshots(cache: WeeklyDataCache, league_instance: League):
    if ml_projector is None:
        raise RuntimeError("ML projector is not initialized")
    week = league_instance.current_week
    live_players = {
        str(player.playerId): player
        for team in league_instance.teams
        for player in team.roster
    }
    for player_id, player_weeks in cache['players'].items():
        week_data = player_weeks.get(str(week))
        player = live_players.get(player_id)
        if (
            not isinstance(week_data, dict)
            or player is None
            or week_data.get('actual') is not None
        ):
            continue
        if week_data.get('espn_projection_before_week') is None:
            week_data['espn_projection_before_week'] = week_data.get('espn_projection')
        if week_data.get('ml_projection_before_week') is not None:
            continue
        try:
            prediction = ml_projector.predict_player(
                player.name,
                player.position,
                player.proTeam,
                season=league_instance.year,
                as_of_week=week,
                opponent=_player_opponent(player, week),
            )
        except Exception as error:
            logger.warning("Unable to snapshot ML projection for %s: %s", player.name, error)
            continue
        if prediction is not None:
            week_data['ml_projection_before_week'] = prediction
            week_data['ml_snapshot_week'] = week


def get_espn_weekly_data():
    """Load and persist ESPN weekly scores/projections without mutating live rosters."""
    if league is None:
        raise RuntimeError("ESPN league is not initialized")

    league_instance = league
    with weekly_data_lock:
        cache = _load_weekly_data_cache(league_instance.year)
        for week in range(1, 19):
            needs_refresh = week in {
                league_instance.current_week,
                league_instance.current_week - 1,
            }
            if week in cache['fetched_weeks'] and not needs_refresh:
                continue

            try:
                week_players = _fetch_espn_weekly_data(league_instance, week)
            except Exception:
                if week < league_instance.current_week:
                    raise
                logger.warning("Unable to fetch ESPN data for week %s", week, exc_info=True)
                continue

            for player_id, scores in week_players.items():
                player_weeks = cache['players'].setdefault(player_id, {})
                existing = player_weeks.get(str(week), {})
                existing.update(scores)
                player_weeks[str(week)] = existing
            cache['fetched_weeks'].add(week)
            _save_weekly_data_cache(cache)

        _capture_current_week_ml_snapshots(cache, league_instance)
        _save_weekly_data_cache(cache)
        return cache['players']


model_refresh_lock = RLock()


def _refresh_models_for_completed_weeks():
    if league is None or ml_projector is None:
        return
    completed_week = league.current_week - 1
    if (
        ml_projector.training_season == league.year
        and ml_projector.training_through_week is not None
        and ml_projector.training_through_week >= completed_week
    ):
        return

    with model_refresh_lock:
        if (
            ml_projector.training_season == league.year
            and ml_projector.training_through_week is not None
            and ml_projector.training_through_week >= completed_week
        ):
            return
        logger.info(
            "Retraining models through completed week %s of season %s",
            completed_week,
            league.year,
        )
        ml_projector.train_models(
            seasons=range(max(2019, league.year - 6), league.year + 1),
            holdout_season=league.year - 1,
            current_season=league.year,
            through_week=league.current_week,
        )
        ml_projector.save_models(
            os.path.join(os.path.dirname(__file__), '..', 'models')
        )


def _projection_comparison(cache: WeeklyDataCache | None, position: str):
    if cache is None:
        raise RuntimeError("Weekly projection cache has not been initialized")
    if league is None:
        raise RuntimeError("ESPN league is not initialized")
    pairs = []
    with weekly_data_lock:
        for player_weeks in cache['players'].values():
            for week_number, week_data in player_weeks.items():
                if (
                    int(week_number) >= league.current_week
                    or week_data.get('position') != position
                    or week_data.get('actual') is None
                    or week_data.get('espn_projection_before_week') is None
                    or week_data.get('ml_projection_before_week') is None
                ):
                    continue
                actual = float(week_data['actual'])
                pairs.append((
                    actual,
                    float(week_data['espn_projection_before_week']),
                    float(week_data['ml_projection_before_week']),
                ))

    espn_mae = (
        sum(abs(espn - actual) for actual, espn, _ in pairs) / len(pairs)
        if pairs else None
    )
    ml_mae = (
        sum(abs(prediction - actual) for actual, _, prediction in pairs) / len(pairs)
        if pairs else None
    )
    minimum_sample = 30
    ml_selected = (
        len(pairs) >= minimum_sample
        and ml_mae is not None
        and espn_mae is not None
        and ml_mae < espn_mae
    )
    return {
        'weeks_evaluated': len(pairs),
        'minimum_sample': minimum_sample,
        'espn_mae': round(espn_mae, 2) if espn_mae is not None else None,
        'ml_mae': round(ml_mae, 2) if ml_mae is not None else None,
        'selected_source': 'ML' if ml_selected else 'ESPN',
        'selection_reason': (
            'ML has lower prospective MAE on the minimum sample'
            if ml_selected
            else 'ESPN remains the default until ML has lower MAE on at least '
                 f'{minimum_sample} prospective player-weeks'
        ),
    }


# Player Predictions
@app.route('/predict/player', methods=['POST'])
def predict_player():
    """
    Predict fantasy points for a specific player
    Request body: {"player_name": "Patrick Mahomes", "position": "QB", "team": "KC"}
    """
    try:
        data = request.get_json(silent=True) or {}
        player_name = data.get('player_name')
        pos = data.get('position')

        if not player_name or not pos:
            return jsonify({"error": "player_name and position are required"}), 400

        if league is None:
            return jsonify({"error": "ESPN league is not initialized"}), 503

        if ml_projector is None:
            return jsonify({"error": "ML projector is not initialized"}), 503

        _refresh_models_for_completed_weeks()
        target_player = None
        for team_obj in league.teams:
            for player in team_obj.roster:
                if (
                    player.name.lower() == player_name.lower()
                    and player.position.upper() == str(pos).upper()
                ):
                    target_player = player
                    break
            if target_player is not None:
                break

        if target_player is None:
            return jsonify({"error": "Player not found"}), 404

        try:
            ml_result = ml_projector.predict_player_with_confidence(
                target_player.name,
                target_player.position,
                target_player.proTeam,
                season=league.year,
                as_of_week=league.current_week,
                opponent=_player_opponent(target_player, league.current_week),
            )
        except Exception as e:
            logger.warning(f"ML prediction failed for {target_player.name}: {e}")
            ml_result = None

        if ml_result is None:
            current_stats = getattr(target_player, 'stats', {}).get(league.current_week, {})
            espn_projection = current_stats.get('projected_points')
            return jsonify({
                "player": target_player.name,
                "position": target_player.position,
                "predicted_points": (
                    round(float(espn_projection), 2)
                    if espn_projection is not None else None
                ),
                "confidence": None,
                "data_source": (
                    "espn_fallback" if espn_projection is not None else "unavailable"
                )
            })

        return jsonify({
            "player": target_player.name,
            "position": target_player.position,
            "predicted_points": ml_result["prediction"],
            "confidence": ml_result["confidence"],
            "data_source": ml_result.get("data_source", "model"),
            "opponent": _player_opponent(target_player, league.current_week),
        })

    except Exception as e:
        logger.error(f"Error predicting player: {e}")
        return jsonify({"error": str(e)}), 500

# Get weekly projections
@app.route('/projections/weekly', methods=['GET'])
def get_weekly_projections():
    """
    Get weekly projections for all players
    """
    try:
        if league is None:
            return jsonify({"error": "ESPN league is not initialized"}), 503
        if ml_projector is None:
            return jsonify({"error": "ML projector is not initialized"}), 503

        _refresh_models_for_completed_weeks()
        weekly_data = get_espn_weekly_data()
        position_comparisons = {
            player.position: _projection_comparison(weekly_data_cache, player.position)
            for team in league.teams
            for player in team.roster
        }
        all_players = []
        for team in league.teams:
            for player in team.roster:
                try:
                    ml_pred = ml_projector.predict_player(
                        player.name,
                        player.position,
                        player.proTeam,
                        season=league.year,
                        as_of_week=league.current_week,
                        opponent=_player_opponent(player, league.current_week),
                    )
                except Exception as error:
                    logger.warning("ML projection failed for %s: %s", player.name, error)
                    ml_pred = None
                week_stats = getattr(player, 'stats', {}).get(league.current_week, {})
                player_week_data = weekly_data.get(str(player.playerId), {}).get(
                    str(league.current_week), {}
                )
                espn_projection = player_week_data.get('espn_projection_before_week')
                if espn_projection is None:
                    espn_projection = week_stats.get('projected_points')
                comparison = position_comparisons[player.position]
                selected_source = comparison['selected_source']
                projected_points = (
                    ml_pred if selected_source == 'ML' else espn_projection
                )
                if projected_points is None:
                    projected_points = ml_pred if ml_pred is not None else espn_projection
                    if projected_points is not None:
                        selected_source = 'ML' if ml_pred is not None else 'ESPN'

                all_players.append({
                    "player_name": player.name,
                    "position": player.position,
                    "team": team.team_name,
                    "projected_points": projected_points,
                    "ml_projection": ml_pred,
                    "espn_projection": espn_projection,
                    "selected_source": (
                        selected_source if projected_points is not None else "unavailable"
                    ),
                    "selection_reason": comparison['selection_reason'],
                    "projection_comparison": comparison,
                    "opponent": _player_opponent(player, league.current_week),
                    "pro_team": player.proTeam,
                    "injury_status": player.injuryStatus,
                    "percent_owned": player.percent_owned
                })
        
        # Sort by projected points
        all_players.sort(key=lambda x: x['projected_points'] or 0, reverse=True)
        
        return jsonify(all_players)
        
    except Exception as e:
        logger.error(f"Error getting weekly projections: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/analytics/player/<int:player_id>', methods=['GET'])
def get_player_analytics(player_id):
    try:
        if league is None:
            return jsonify({"error": "ESPN league is not initialized"}), 503
        if ml_projector is None:
            return jsonify({"error": "ML projector is not initialized"}), 503

        _refresh_models_for_completed_weeks()
        target_player = None

        for team in league.teams:
            for player in team.roster:
                if player.playerId == player_id:
                    target_player = player
                    break

        if target_player is None:
            return jsonify({"error": "Player not found"}), 404

        espn_weekly_data = get_espn_weekly_data()
        player_weekly_data = espn_weekly_data.get(str(target_player.playerId), {})
        position = target_player.position
        current_week = getattr(league, 'current_week', 1)
        projection_comparison = _projection_comparison(
            weekly_data_cache, position
        )
        current_opponent = _player_opponent(target_player, current_week)

        try: 
            ml_result = ml_projector.predict_player_with_confidence(
                target_player.name,
                position,
                target_player.proTeam,
                season=league.year,
                as_of_week=current_week,
                opponent=current_opponent,
            )
        except Exception as e:
            logger.warning(f"ML prediction failed for {target_player.name}: {e}")
            ml_result = None

        if ml_result is None:
            ml_result = {
                "prediction": None,
                "lower_bound": None,
                "upper_bound": None,
                "confidence": None,
                "data_source": "unavailable",
            }

        history = []
        for week in range(1, 19):
            week_data = player_weekly_data.get(str(week), {})
            actual = week_data.get('actual')
            espn_proj = week_data.get('espn_projection_before_week')
            item = {
                "week": week,
                "actual": (
                    round(float(actual), 2)
                    if actual is not None and week < current_week else None
                ),
                "espn_projection": (
                    round(float(espn_proj), 2) if espn_proj is not None else None
                ),
            }

            if week_data.get('ml_projection_before_week') is not None:
                item['ml_projection'] = round(
                    float(week_data['ml_projection_before_week']), 2
                )

            history.append(item)

        history.sort(key=lambda i: i["week"])

        recent_actuals = [
            item["actual"] for item in history
            if item["actual"] is not None
        ]

        recent_avg = (
            sum(recent_actuals[-5:]) / len(recent_actuals[-5:])
            if recent_actuals
            else None
        )

        future_forecast = []
        for week in range(current_week, 19):
            try:
                p = ml_projector.predict_player_with_confidence(
                    target_player.name, position, target_player.proTeam,
                    season=league.year, as_of_week=week,
                    opponent=_player_opponent(target_player, week),
                )
            except Exception as e:
                logger.warning(f"Forecast failed week {week}: {e}")
                p = None

            week_data = player_weekly_data.get(str(week), {})
            espn = week_data.get('espn_projection_before_week')
            if espn is None:
                espn = week_data.get('espn_projection')
            if espn is not None:
                espn = round(float(espn), 2)

            if p is None or p.get("bye"):
                future_forecast.append({"week": week, "bye": p is not None, "espn_projection": espn,
                                        "ml_projection": None, "preferred_projection": espn,
                                        "preferred_source": "ESPN" if espn is not None else "unavailable",
                                        "lower_bound": None, "upper_bound": None})
            else:
                selected_source = projection_comparison['selected_source']
                preferred = p["prediction"] if selected_source == 'ML' else espn
                if preferred is None:
                    preferred = p['prediction']
                    selected_source = 'ML'
                future_forecast.append({"week": week, "bye": False, "opponent": p.get("opponent"),
                                        "espn_projection": espn, "ml_projection": p["prediction"],
                                        "preferred_projection": preferred,
                                        "preferred_source": selected_source,
                                        "lower_bound": p["lower_bound"], "upper_bound": p["upper_bound"]})

        current_week_data = player_weekly_data.get(str(current_week), {})
        current_espn_projection = current_week_data.get(
            'espn_projection_before_week',
            current_week_data.get('espn_projection'),
        )
        if current_espn_projection is None:
            current_espn_projection = getattr(
                target_player, 'stats', {}
            ).get(current_week, {}).get('projected_points')
        current_selected_source = projection_comparison['selected_source']
        if current_selected_source == 'ML' and ml_result['prediction'] is None:
            current_selected_source = (
                'ESPN' if current_espn_projection is not None else 'unavailable'
            )
        elif current_selected_source == 'ESPN' and current_espn_projection is None:
            current_selected_source = (
                'ML' if ml_result['prediction'] is not None else 'unavailable'
            )
        current_projection = (
            ml_result['prediction']
            if current_selected_source == 'ML'
            else current_espn_projection
        )

        return jsonify({
            "player_id": player_id,
            "player_name": target_player.name,
            "position": position,
            "team": target_player.proTeam,
            "current_week": current_week,
            "recent_average": round(recent_avg, 2) if recent_avg is not None else None,
            "current_projection": current_projection,
            "current_selected_source": current_selected_source,
            "current_ml_projection": ml_result["prediction"],
            "current_espn_projection": current_espn_projection,
            "confidence": ml_result["confidence"],
            "data_source": (
                "model" if current_selected_source == "ML"
                else "espn_fallback" if current_selected_source == "ESPN"
                else "unavailable"
            ),
            "history": history,
            "projection_comparison": projection_comparison,
            "future_forecast": future_forecast
        })

    except Exception as error:
        logger.error(f"Error getting player analytics: {error}")
        return jsonify({"error": str(error)}), 500


# Fetch cirrent standings
@app.route('/standings', methods=['GET'])
def get_standings():
    try:
        if league is None:
            return jsonify({"error": "ESPN league is not initialized"}), 503

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
        if league is None:
            return jsonify({"error": "ESPN league is not initialized"}), 503

        matchups = league.box_scores()
        matchup_data = []
        for match in matchups:
            matchup_data.append({
                "home_team": match.home_team.team_name if match.home_team else None,
                "home_score": match.home_score,
                "home_prodj": match.home_projected,
                "away_team": match.away_team.team_name if match.away_team else None,
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
        if league is None:
            return jsonify({"error": "ESPN league is not initialized"}), 503

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
        if league is None:
            return jsonify({"error": "ESPN league is not initialized"}), 503

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