import os
import json
import warnings
from datetime import datetime
from typing import Any

import joblib
import numpy as np
import pandas as pd
import nflreadpy as nfl
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

warnings.filterwarnings('ignore')


def _default_training_seasons(n=6):
    """Last `n` COMPLETED seasons (the current season is still in progress)."""
    last_complete = datetime.now().year - 1
    return tuple(range(last_complete - n + 1, last_complete + 1))


class NFLPlayerProjector:
    """
    Weekly fantasy-point projector.

    Design rules (these are what fix the old bugs):
      * Every feature is a LAGGED rolling average -- it only uses games played
        BEFORE the game being predicted.
      * Training and inference build features the exact same way, from the same
        window of games (rolling across seasons, no season-only / career-count
        mismatches).
      * Evaluation is a time-based holdout (train on past seasons, test on the
        latest), compared against a naive "last 5 games average" baseline.
      * The prediction interval comes from real holdout residuals, not from the
        disagreement between trees.
    """

    POSITIONS = ('QB', 'RB', 'WR', 'TE')

    # ESPN stat IDs used by the nflreadpy weekly player-stat feed.
    SCORING_STAT_COLUMNS = {
        0: 'passing_att',
        1: 'passing_completions',
        3: 'passing_yds',
        4: 'passing_td',
        19: 'passing_2pt_conversions',
        20: 'passing_interceptions',
        23: 'carries',
        24: 'rushing_yds',
        25: 'rushing_td',
        26: 'rushing_2pt_conversions',
        40: 'rushing_yds',
        41: 'receptions',
        42: 'receiving_yds',
        43: 'receiving_td',
        44: 'receiving_2pt_conversions',
        53: 'receptions',
        58: 'targets',
        59: 'receiving_yards_after_catch',
        63: 'fumble_recovery_tds',
        64: 'sacks_suffered',
        68: 'fumbles_total',
        72: 'fumbles_lost_total',
        22: 'passing_yds',
        61: 'receiving_yds',
        102: 'pt_return_tds',
    }

    SCORING_BONUS_IDS = {17, 18, 37, 38, 56, 57}
    UNSUPPORTED_OFFENSIVE_SCORING_IDS = {
        2, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 21, 27, 28, 29,
        30, 31, 32, 33, 34, 35, 36, 39, 45, 46, 47, 48, 49, 50, 51, 52,
        60, 62, 65, 66, 67, 69, 70, 71, 73,
    }

    # Raw per-game stat columns (after renaming). Missing ones are created as 0.
    STAT_COLUMNS = [
        'passing_yds', 'passing_td', 'passing_att', 'passing_completions',
        'passing_interceptions', 'passing_2pt_conversions',
        'rushing_yds', 'rushing_td', 'rushing_2pt_conversions', 'carries',
        'receiving_yds', 'receiving_td', 'receiving_2pt_conversions',
        'receptions', 'targets', 'receiving_yards_after_catch',
        'fumble_recovery_tds', 'fumbles_total', 'fumbles_lost_total',
        'sacks_suffered', 'special_teams_tds', 'pt_return_tds',
    ]

    # stat -> rolling window sizes. Feature name: avg_{stat}_last_{window}
    ROLLING_SPEC = {
        'passing_yds': (5,),
        'rushing_yds': (5,),
        'receiving_yds': (5,),
        'receptions': (5,),
        'targets': (5,),
        'fantasy_points': (3, 5),
    }

    POSITION_FEATURES = {
        'QB': [
            'avg_passing_yds_last_5', 'avg_rushing_yds_last_5',
            'avg_fantasy_points_last_3', 'avg_fantasy_points_last_5',
            'avg_opponent_points_allowed_last_5',
        ],
        'RB': [
            'avg_rushing_yds_last_5', 'avg_receiving_yds_last_5',
            'avg_receptions_last_5', 'avg_targets_last_5',
            'avg_fantasy_points_last_3', 'avg_fantasy_points_last_5',
            'avg_opponent_points_allowed_last_5',
        ],
        'WR': [
            'avg_receiving_yds_last_5', 'avg_receptions_last_5',
            'avg_targets_last_5', 'avg_rushing_yds_last_5',
            'avg_fantasy_points_last_3', 'avg_fantasy_points_last_5',
            'avg_opponent_points_allowed_last_5',
        ],
        'TE': [
            'avg_receiving_yds_last_5', 'avg_receptions_last_5',
            'avg_targets_last_5', 'avg_rushing_yds_last_5',
            'avg_fantasy_points_last_3', 'avg_fantasy_points_last_5',
            'avg_opponent_points_allowed_last_5',
        ],
    }

    TEAM_ALIASES = {'LAR': 'LA', 'WSH': 'WAS'}

    def __init__(self, scoring_format: list[dict[str, Any]]):
        if not scoring_format:
            raise ValueError("ESPN league scoring settings are required to train projections")

        self.scoring_rules = {
            int(rule['id']): float(rule['points'])
            for rule in scoring_format
        }
        self.models = {}
        self.feature_columns = {}
        self.residual_std = {}
        self.metrics = {}
        self.last_trained = None
        self.training_season = None
        self.training_through_week = None
        self._history_cache = {}

    # ------------------------------------------------------------------ #
    # Data
    # ------------------------------------------------------------------ #
    def fetch_historical_data(self, seasons=None):
        """Load weekly player stats for the given seasons and engineer features."""
        seasons = tuple(sorted(seasons)) if seasons else _default_training_seasons()
        print(f"Fetching data for seasons: {list(seasons)}")

        raw = nfl.load_player_stats(list(seasons), summary_level='week').to_dicts()
        df = pd.DataFrame(raw)

        df = df.rename(columns={
            'passing_yards': 'passing_yds',
            'passing_tds': 'passing_td',
            'attempts': 'passing_att',
            'completions': 'passing_completions',
            'rushing_yards': 'rushing_yds',
            'rushing_tds': 'rushing_td',
            'receiving_yards': 'receiving_yds',
            'receiving_tds': 'receiving_td',
        })

        # Regular season only, skill positions only
        if 'season_type' in df.columns:
            df = df[df['season_type'] == 'REG']
        df = df[df['position'].isin(self.POSITIONS)].copy()

        df = self._engineer_features(df)
        self._history_cache[seasons] = df
        return df

    def _compute_fantasy_points(self, df):
        """Score nflreadpy weekly stats with the active ESPN league rules."""
        points = pd.Series(0.0, index=df.index)
        for stat_id, weight in self.scoring_rules.items():
            if not weight:
                continue

            stat_column = self.SCORING_STAT_COLUMNS.get(stat_id)
            if stat_column:
                points += df[stat_column] * weight
                continue

            if stat_id == 101:
                kickoff_return_tds = (
                    df['special_teams_tds'] - df['pt_return_tds']
                ).clip(lower=0)
                points += kickoff_return_tds * weight
                continue

            if stat_id in self.SCORING_BONUS_IDS:
                if stat_id == 17:
                    bonus = df['passing_yds'].between(300, 399)
                elif stat_id == 18:
                    bonus = df['passing_yds'] >= 400
                elif stat_id == 37:
                    bonus = df['rushing_yds'].between(100, 199)
                elif stat_id == 38:
                    bonus = df['rushing_yds'] >= 200
                elif stat_id == 56:
                    bonus = df['receiving_yds'].between(100, 199)
                else:
                    bonus = df['receiving_yds'] >= 200
                points += bonus.astype(float) * weight
                continue

            if stat_id == 62:
                points += (
                    df['passing_2pt_conversions']
                    + df['rushing_2pt_conversions']
                    + df['receiving_2pt_conversions']
                ) * weight
                continue

            if stat_id == 73:
                points += (
                    df['passing_interceptions'] + df['fumbles_lost_total']
                ) * weight
                continue

            if stat_id in self.UNSUPPORTED_OFFENSIVE_SCORING_IDS:
                raise ValueError(
                    f"ESPN scoring stat {stat_id} is not supported by the "
                    "nflreadpy weekly player data"
                )

        return points

    def _engineer_features(self, df):
        """
        Build fantasy_points and LAGGED rolling averages.

        Rolling is computed per player ACROSS seasons and shifted by one game,
        so a row's features only reflect games before it.
        """
        df = df.sort_values(['player_id', 'season', 'week']).reset_index(drop=True)

        missing_stats = [col for col in self.STAT_COLUMNS if col not in df.columns]
        if missing_stats:
            raise ValueError(f"nflreadpy data is missing required stats: {missing_stats}")

        for col in self.STAT_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df['fantasy_points'] = self._compute_fantasy_points(df)

        grouped = df.groupby('player_id')
        for stat, windows in self.ROLLING_SPEC.items():
            for window in windows:
                df[f'avg_{stat}_last_{window}'] = grouped[stat].transform(
                    lambda s, w=window: s.shift(1).rolling(w, min_periods=1).mean()
                )

        if 'opponent_team' not in df.columns or 'game_id' not in df.columns:
            raise ValueError("nflreadpy data is missing weekly opponent/game identifiers")
        game_keys = ['opponent_team', 'position', 'season', 'week', 'game_id']
        defensive_games = (
            df.groupby(game_keys, as_index=False, dropna=False)['fantasy_points']
            .sum()
            .sort_values(['opponent_team', 'position', 'season', 'week'])
        )
        defense_groups = defensive_games.groupby(
            ['opponent_team', 'position']
        )['fantasy_points']
        defensive_games['avg_opponent_points_allowed_last_5'] = defense_groups.transform(
            lambda scores: scores.shift(1).rolling(5, min_periods=1).mean()
        )
        df = df.merge(
            defensive_games[game_keys + ['avg_opponent_points_allowed_last_5']],
            on=game_keys,
            how='left',
            validate='many_to_one',
        )

        return df

    def _name_column(self, df):
        for candidate in ('player_display_name', 'player_name', 'full_name'):
            if candidate in df.columns:
                return candidate
        return None

    # ------------------------------------------------------------------ #
    # Training
    # ------------------------------------------------------------------ #
    def prepare_training_data(self, df, position):
        """Features and target for one position. Only pre-game info is used."""
        if position not in self.POSITION_FEATURES:
            raise ValueError(f"Unsupported position: {position}")
        candidate_features = self.POSITION_FEATURES[position]

        pos_df = df[df['position'] == position]
        missing = [f for f in candidate_features if f not in pos_df.columns]
        if missing:
            raise ValueError(f"Missing feature columns for {position}: {missing}")

        x = pos_df[candidate_features].dropna()   # drops each player's first game
        y = pos_df.loc[x.index, 'fantasy_points']
        return x, y

    def _make_model(self):
        # Shallower trees + bigger leaves: weekly fantasy scoring is very noisy,
        # so a deep forest just memorises noise.
        return RandomForestRegressor(
            n_estimators=300,
            max_depth=8,
            min_samples_split=20,
            min_samples_leaf=15,
            max_features=0.7,
            random_state=42,
            n_jobs=-1,
        )

    def train_models(
        self,
        positions=POSITIONS,
        seasons=None,
        holdout_season=None,
        current_season=None,
        through_week=None,
    ):
        """
        Train one model per position, evaluated on a time-based holdout.

        `through_week` excludes the named `current_season`'s in-progress week
        and future weeks from model fitting. If given, holdout evaluation is
        performed on `holdout_season` and final models are fit on all available
        rows up to that cutoff.
        """
        self.models.clear()
        self.feature_columns.clear()
        self.residual_std.clear()
        self.metrics.clear()

        seasons = tuple(sorted(seasons)) if seasons else _default_training_seasons()
        if current_season is not None:
            seasons = tuple(sorted(set(seasons) | {current_season}))
        print("Fetching historical data...")
        df = self.fetch_historical_data(seasons)
        if current_season is not None and through_week is not None:
            df = df[
                (df['season'] < current_season)
                | ((df['season'] == current_season) & (df['week'] < through_week))
            ].copy()
        holdout_season = holdout_season or max(seasons)

        for pos in positions:
            print(f"\nTraining model for {pos}...")
            x, y = self.prepare_training_data(df, pos)

            if len(x) < 200:
                print(f"Not enough data for {pos}, skipping...")
                continue

            # ---- time-based split ----
            season_col = df.loc[x.index, 'season']
            if len(seasons) > 1:
                train_mask = season_col < holdout_season
                test_mask = season_col == holdout_season
            else:
                time_key = season_col * 100 + df.loc[x.index, 'week']
                train_mask = time_key <= time_key.quantile(0.8)
                test_mask = ~train_mask

            x_train, y_train = x[train_mask], y[train_mask]
            x_test, y_test = x[test_mask], y[test_mask]

            if len(x_train) < 100 or len(x_test) < 30:
                print(f"Split too small for {pos}, skipping...")
                continue

            eval_model = self._make_model().fit(x_train, y_train)
            y_pred = eval_model.predict(x_test)

            mae = mean_absolute_error(y_test, y_pred)
            rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
            baseline_mae = mean_absolute_error(y_test, x_test['avg_fantasy_points_last_5'])
            resid_std = float(np.std(y_test.values - y_pred))

            print(f"Holdout (season {holdout_season}): MAE {mae:.2f} | RMSE {rmse:.2f}")
            print(f"Baseline (last-5 avg) MAE: {baseline_mae:.2f} "
                  f"-> model is {'BETTER' if mae < baseline_mae else 'WORSE'} than baseline")

            # ---- refit on everything for production ----
            model = self._make_model().fit(x, y)

            self.models[pos] = model
            self.feature_columns[pos] = x.columns.tolist()
            self.residual_std[pos] = resid_std
            self.metrics[pos] = {
                'holdout_mae': round(float(mae), 3),
                'holdout_rmse': round(rmse, 3),
                'baseline_mae': round(float(baseline_mae), 3),
                'residual_std': round(resid_std, 3),
                'holdout_season': int(holdout_season),
            }

            importance = pd.DataFrame({
                'feature': x.columns,
                'importance': model.feature_importances_,
            }).sort_values('importance', ascending=False)
            print("Top features:")
            print(importance.head(5).to_string(index=False))

        self.last_trained = datetime.now()
        self.training_season = current_season or max(seasons)
        self.training_through_week = (
            through_week - 1 if current_season is not None and through_week is not None
            else None
        )
        if not self.models:
            raise RuntimeError("No position models could be trained from nflreadpy data")

        print("\nTraining complete!")
        return self

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #
    def _load_live_history(self, season):
        """Previous + current season, so early-season predictions have data."""
        key = (season - 1, season)
        if key in self._history_cache:
            return self._history_cache[key]

        print(f"Fetching {key} week-level data for live lookups...")
        try:
            return self.fetch_historical_data(key)
        except Exception as error:
            # Current season may not be published yet -- fall back to last season
            print(f"Could not load {key}: {error}. Trying {season - 1} only.")
            return self.fetch_historical_data((season - 1,))

    def _get_player_recent_form(
        self, player_name, position, season=None, as_of_week=None, opponent=None
    ):
        """
        Build the same lagged feature vector used in training, from the player's
        actual games strictly before `as_of_week` of `season` (or every game so
        far if as_of_week is None). Looks back across seasons.

        Returns (features_dict, n_games) or (None, 0) if no games are found.
        """
        season = season or datetime.now().year
        df = self._load_live_history(season)

        name_col = self._name_column(df)
        if name_col is None:
            return None, 0

        games = df[
            (df[name_col].str.lower().str.strip() == player_name.lower().strip())
            & (df['position'] == position)
        ]

        if as_of_week is not None:
            games = games[
                (games['season'] < season)
                | ((games['season'] == season) & (games['week'] < as_of_week))
            ]
        else:
            games = games[games['season'] <= season]

        games = games.sort_values(['season', 'week'])
        if games.empty:
            return None, 0

        form = {}
        for stat, windows in self.ROLLING_SPEC.items():
            for window in windows:
                form[f'avg_{stat}_last_{window}'] = float(games[stat].tail(window).mean())

        form['avg_opponent_points_allowed_last_5'] = self._get_opponent_form(
            df, opponent, position, season, as_of_week
        )
        return form, len(games)

    def _get_opponent_form(self, df, opponent, position, season, as_of_week):
        games = df[df['position'] == position]
        if opponent:
            opponent = self.TEAM_ALIASES.get(opponent, opponent)
            games = games[games['opponent_team'] == opponent]
        if as_of_week is not None:
            games = games[
                (games['season'] < season)
                | ((games['season'] == season) & (games['week'] < as_of_week))
            ]

        allowed = games.groupby(
            ['game_id', 'season', 'week'], as_index=False
        )['fantasy_points'].sum().sort_values(['season', 'week'])
        if as_of_week is not None:
            allowed = allowed[
                (allowed['season'] < season)
                | ((allowed['season'] == season) & (allowed['week'] < as_of_week))
            ]
        if not allowed.empty:
            return float(allowed['fantasy_points'].tail(5).mean())

        position_games = df[df['position'] == position].groupby(
            ['game_id', 'season', 'week'], as_index=False
        )['fantasy_points'].sum().sort_values(['season', 'week'])
        if as_of_week is not None:
            position_games = position_games[
                (position_games['season'] < season)
                | (
                    (position_games['season'] == season)
                    & (position_games['week'] < as_of_week)
                )
            ]
        if position_games.empty:
            raise ValueError(f"No historical opponent data is available for {position}")
        return float(position_games['fantasy_points'].tail(5).mean())

    def predict_player_with_confidence(
        self, player, pos, team, season=None, as_of_week=None, opponent=None
    ):
        """Predict points for a single player, with a range and confidence."""
        if pos not in self.models:
            print(f"No model trained for {pos}")
            return None

        features = self.feature_columns[pos]

        form, n_games = self._get_player_recent_form(
            player, pos, season=season, as_of_week=as_of_week, opponent=opponent
        )
        if form is None:
            return None

        # DataFrame (not a bare list) keeps column names, avoiding sklearn warnings
        row = pd.DataFrame([[form[f] for f in features]], columns=features)

        prediction = float(self.models[pos].predict(row)[0])
        std = self.residual_std[pos]

        games_factor = min(1.0, n_games / 5)
        confidence = min(0.95, max(0.35, (1 - std / max(prediction, 1)) * games_factor))

        return {
            'prediction': round(prediction, 2),
            'lower_bound': round(max(0.0, prediction - std), 2),
            'upper_bound': round(prediction + std, 2),
            'confidence': round(confidence, 2),
            'data_source': 'recent_games',
            'games_used': n_games,
        }

    def predict_player(
        self, player, pos, team, season=None, as_of_week=None, opponent=None
    ):
        """Point estimate used by the weekly projections endpoint."""
        result = self.predict_player_with_confidence(
            player, pos, team, season=season, as_of_week=as_of_week, opponent=opponent
        )
        return result['prediction'] if result else None

    def predict_roster(self, roster_data):
        """Predict points for an entire roster."""
        predictions = []
        for player in roster_data:
            pred = self.predict_player(
                player['name'],
                player['position'],
                player.get('pro_team', ''),
            )
            predictions.append({
                'player': player['name'],
                'position': player['position'],
                'predicted_points': pred,
            })
        return predictions

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save_models(self, path='models/'):
        os.makedirs(path, exist_ok=True)

        for position, model in self.models.items():
            joblib.dump(model, os.path.join(path, f'model_{position}.pkl'))

        with open(os.path.join(path, 'feature_columns.txt'), 'w') as f:
            for position, cols in self.feature_columns.items():
                f.write(f'{position}: {",".join(cols)}\n')

        with open(os.path.join(path, 'meta.json'), 'w') as f:
            json.dump({
                'residual_std': self.residual_std,
                'metrics': self.metrics,
                'scoring_signature': json.dumps(sorted(self.scoring_rules.items())),
                'training_season': self.training_season,
                'training_through_week': self.training_through_week,
                'trained_at': self.last_trained.isoformat() if self.last_trained else None,
            }, f, indent=2)

    def load_models(self, path='models/'):
        """
        Load trained models. Raises if the saved files are stale (old feature
        schema or missing metadata) so the caller can retrain.
        """
        for pos in self.POSITIONS:
            model_path = os.path.join(path, f'model_{pos}.pkl')
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Saved model for {pos} was not found")
            self.models[pos] = joblib.load(model_path)

        feature_path = os.path.join(path, 'feature_columns.txt')
        if os.path.exists(feature_path):
            with open(feature_path, 'r') as file:
                for line in file:
                    if ': ' in line:
                        pos, cols = line.strip().split(': ')
                        self.feature_columns[pos] = cols.split(',')

        meta_path = os.path.join(path, 'meta.json')
        if not os.path.exists(meta_path):
            raise ValueError("Saved models are missing meta.json (outdated) -- retrain")
        with open(meta_path, 'r') as file:
            meta = json.load(file)
        scoring_signature = json.dumps(sorted(self.scoring_rules.items()))
        if meta.get('scoring_signature') != scoring_signature:
            raise ValueError("Saved models use different ESPN league scoring settings")
        self.residual_std = meta.get('residual_std', {})
        self.metrics = meta.get('metrics', {})
        self.training_season = meta.get('training_season')
        self.training_through_week = meta.get('training_through_week')

        for pos in self.models:
            expected = self.POSITION_FEATURES.get(pos)
            if self.feature_columns.get(pos) != expected:
                raise ValueError(f"Saved {pos} model uses an outdated feature schema")
            if pos not in self.residual_std:
                raise ValueError(f"Saved {pos} model is missing holdout residuals")