import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
import nflreadpy as nfl
import joblib
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

class NFLPlayerProjector:

    RAW_BASE_COLUMNS = [
        'passing_yds', 'passing_td', 'passing_att',
        'rushing_yds', 'rushing_td',
        'receiving_yds', 'receiving_td', 'receptions',
    ]

    ROLLING_STATS = [
        'passing_yds', 'rushing_yds', 'receiving_yds',
        'receptions', 'fantasy_points',
    ]

    POSITION_FEATURES = {
        'QB': [
            'avg_passing_yds_last_5', 'avg_rushing_yds_last_5',
            'avg_fantasy_points_last_5', 'games_played', 'age',
        ],
        'RB': [
            'avg_receiving_yds_last_5', 'avg_rushing_yds_last_5',
            'avg_receptions_last_5', 'avg_fantasy_points_last_5',
            'games_played', 'age',
        ],
        'WR': [
            'avg_receiving_yds_last_5', 'avg_rushing_yds_last_5',
            'avg_receptions_last_5', 'avg_fantasy_points_last_5',
            'games_played', 'age',
        ],
        'TE': [
            'avg_receiving_yds_last_5', 'avg_rushing_yds_last_5',
            'avg_receptions_last_5', 'avg_fantasy_points_last_5',
            'games_played', 'age',
        ],
    }

    def __init__(self):
        self.models= {}
        self.scalers = {}
        self.feature_columns = {}
        self.last_trained = None
        self._history_cache = {}

    def fetch_historical_data(self, seasons=(2020, 2021, 2022, 2023, 2024, 2025)):
        """
        Historcal data for training
        """
        seasons = list(seasons)
        print(f"Fetching data for seasons: {seasons}")

        player_stats = nfl.load_player_stats(
            seasons,
            summary_level='week'
        ).to_dicts()

        player_stats = pd.DataFrame(player_stats)

        merged_data = player_stats.rename(columns={
            'passing_yards': 'passing_yds',
            'passing_tds': 'passing_td',
            'attempts': 'passing_att',
            'rushing_yards': 'rushing_yds',
            'rushing_tds': 'rushing_td',
            'receiving_yards': 'receiving_yds',
            'receiving_tds': 'receiving_td'
        })

        merged_data = self._engineer_features(merged_data)
        self._history_cache[tuple(sorted(seasons))] = merged_data

        return merged_data

    def _engineer_features(self, df):
        """
        Create fantasy_points and LAGGED rolling averages.

        Rolling averages are shifted by one game per player so that the
        feature for a given row only reflects games that happened BEFORE
        that row -- never the row's own outcome. This is what makes the
        features usable at prediction time, before a game has been played.
        """

        df = df.sort_values(['player_id', 'season', 'week']).reset_index(drop=True)

        df['fantasy_points'] = (
            df.get('passing_yds') * 0.04 
            + df.get('passing_td') * 4 
            + df.get('rushing_yds') * 0.01 
            + df.get('rushing_td') * 6 
            + df.get('receiving_yds') * 0.1 
            + df.get('receiving_td') * 6 
            + df.get('receptions') * 1
        )

        # Games player BEFORE this one (also lagged)
        df['games_played'] = df.groupby('player_id').cumcount()

        # Calculate per-game avgs
        for stat in self.ROLLING_STATS:
            if stat in df.columns:
                df[f'avg_{stat}_last_5'] = (
                    df.groupby('player_id')[stat]
                    .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
                )

        if 'birth_date' in df.columns:
            df['age'] = pd.to_datetime(df['season'], format='%Y') - pd.to_datetime(df['birth_date']).dt.year

        return df

    def prepare_training_data(self, df, position):
        """
        Prepare leakage-free features and targets for a position.
 
        Only pre-game-known information is used as a feature: lagged
        rolling averages, games played so far, and age. Current-game raw
        stats (passing_yds, rushing_td, etc.) are NEVER included -- they
        are what we're trying to predict, not predict from.
        """

        pos_df = df[df['position'] == position].copy()

        candidate_features = self.POSITION_FEATURES.get(position)
        if candidate_features is None:
            return None, None

        features = [feat for feat in candidate_features if feat in pos_df.columns]
        target = 'fantasy_points'

        x = pos_df[features].dropna()
        y = pos_df.loc[x.index, target]

        return x, y

    def train_models(self, positions=['QB', 'RB', 'WR', 'TE'], seasons=[2020, 2021, 2022, 2023, 2024, 2025]):
        """
        Train separate models for each pos
        """
        print("Fetching historical data...")

        df=self.fetch_historical_data(seasons)

        for pos in positions:
            print(f"\nTraining model for {pos}...")

            x, y = self.prepare_training_data(df, pos)

            if x is None or len(x) < 50:
                print(f"None enough data for {pos}, skipping...")
                continue

            scaler = StandardScaler()
            x_scaled = scaler.fit_transform(x)

            # Tain the model
            model = RandomForestRegressor(
                n_estimators=200,
                max_depth=15,
                min_samples_split=10,
                min_samples_leaf=5,
                random_state=42,
                n_jobs=-1
            )

            # Cross-validation
            cv_scores = cross_val_score(model, x_scaled, y, cv=5, scoring='r2')
            print(f"CV R^2 scores: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")

            # Train on full dataset
            model.fit(x_scaled, y)

            # Store the model and scaler
            self.models[pos] = model
            self.scalers[pos] = scaler
            self.feature_columns[pos] = x.columns.tolist()

            # Eval
            y_pred = model.predict(x_scaled)
            mae = mean_absolute_error(y, y_pred)
            rmse = np.sqrt(mean_squared_error(y, y_pred))
            print(f"MAE: {mae:.2f}, RMSE: {rmse:.2f}")

            # Feature importance
            feat_importance = pd.DataFrame({
                'feature': x.columns,
                'importance': model.feature_importances_
            }).sort_values('importance', ascending=False)
            print("Top 5 features:")
            print(feat_importance.head(5))

        self.last_trained = datetime.now()
        print("\nTraining complete!")

        return self

    def _get_player_recent_form(self, player_name, position, season=None, as_of_week=None):
        """
        Finding the players most recent game history and build the same lagged feature vector
        used in training, bassed on the acutal games.

        Returns a dict of {feature_name: value} using only games strictly
        before `as_of_week` (or all games played so far in `season` if
        as_of_week is None), falling back to positional league-average
        defaults for rookies / players with no logged games yet.
        """
        season = season or datetime.now().year
        cache_key = (season,)

        if cache_key not in self._history_cache:
            print(f"Fetching {season} week-level data for live lookups...")
            df = self.fetch_historical_data([season])
        else:
            df = self._history_cache[cache_key]


        name_col = None
        for candidate in ('player_display_name', 'player_name', 'full_name'):
            if candidate in df.columns:
                name_col = candidate
                break

        if name_col is None:
            player_games = pd.DataFrame()
        else:
            player_games = df[(df[name_col].str.lower() == player_name.lower()) & (df['position'] == position)].sort_values('week')

        if as_of_week is not None:
            player_games = player_games[player_games['week'] < as_of_week]

        if player_games.empty:
            return None

        latest = player_games.iloc[-1]

        form = {}
        for stat in self.ROLLING_STATS:
            col = f'avg_{stat}_last_5'
            if col in player_games.columns:
                recent = player_games[stat].tail(5)
                form[col] = float(recent.mean()) if len(recent) else np.nan

        form['games_played'] = len(player_games)
        if 'age' in player_games.columns and pd.notna(latest.get('age')):
            form['age'] = float(latest['age'])

        return form

    def predict_player_with_confidence(self, player, pos, team, season=None, as_of_week=None):
        """"
        Predict points for a single player
        """

        if pos not in self.models:
            print(f"No model trained for {pos}")
            return None

        features = self.feature_columns[pos]

        position_fallback_defaults = {
            'QB': {
                'avg_passing_yds_last_5': 220, 'avg_rushing_yds_last_5': 15,
                'avg_fantasy_points_last_5': 15, 'games_played': 0, 'age': 25,
            },
            'RB': {
                'avg_receiving_yds_last_5': 15, 'avg_rushing_yds_last_5': 45,
                'avg_receptions_last_5': 2, 'avg_fantasy_points_last_5': 8,
                'games_played': 0, 'age': 25,
            },
            'WR': {
                'avg_receiving_yds_last_5': 40, 'avg_rushing_yds_last_5': 2,
                'avg_receptions_last_5': 3, 'avg_fantasy_points_last_5': 8,
                'games_played': 0, 'age': 25,
            },
            'TE': {
                'avg_receiving_yds_last_5': 25, 'avg_rushing_yds_last_5': 0,
                'avg_receptions_last_5': 2, 'avg_fantasy_points_last_5': 6,
                'games_played': 0, 'age': 25,
            },
        }

        form = self._get_player_recent_form(player, pos, season=season, as_of_week=as_of_week)
        data_source = "recent_games"

        if form is None:
            print(f"No logged games found for {player} ({pos}) -- using positional avgs")
            form = position_fallback_defaults.get(pos, {})
            data_source = "positional_fallback"


        defaults = position_fallback_defaults.get(pos, {})
        feature_vector = [
            form.get(feature, defaults.get(feature, 0))
            for feature in features
        ]

        scaled = self.scalers[pos].transform([feature_vector])
        model = self.models[pos]

        tree_predictions = np.array([
            estimator.predict(scaled)[0]
            for estimator in model.estimators_
        ])

        prediction = float(tree_predictions.mean())
        std = float(tree_predictions.std())

        return {
            "prediction": round(prediction, 2),
            "lower_bound": round(max(0, prediction - std), 2),
            "upper_bound": round(prediction + std, 2),
            "confidence": round(
                min(0.95, max(0.35, 1- std/max(prediction,1))), 2
            ),
            "data_source": data_source
        }

    def predict_player(self, player, pos, team, season=None, as_of_week=None):
        """Return the point estimate used by the weekly projections endpoint."""
        result = self.predict_player_with_confidence(player, pos, team, season=season, as_of_week=as_of_week)
        return result["prediction"] if result else None
    
    def predict_roster(self, roster_data):
        """
        Predict points for entire roster
        """
        predictions = []
        for player in roster_data:
            pred = self.predict_player(
                player['name'],
                player['position'],
                player.get('pro_team', '')
            )
            predictions.append({
                'player': player['name'],
                'position': player['position'],
                'predicted_points': pred
            })

        return predictions

    def save_models(self, path='models/'):
        """
        Save trained models to disk
        """
        os.makedirs(path, exist_ok=True)

        for position in self.models:
            joblib.dump(self.models[position], f'{path}/model_{position}.pkl')
            joblib.dump(self.scalers[position], f'{path}/scaler_{position}.pkl')

        with open(f'{path}/feature_columns.txt', 'w') as f:
            for position, cols in self.feature_columns.items():
                f.write(f'{position}: {",".join(cols)}\n')

    def load_models(self, path='models/'):
        """
        Load trained models from disk
        """
        for pos in ['QB', 'RB', 'TE', 'WR']:
            model_path = f'{path}/model_{pos}.pkl'
            scaler_path = f'{path}/scaler_{pos}.pkl'

            if os.path.exists(model_path) and os.path.exists(scaler_path):
                self.models[pos] = joblib.load(model_path)
                self.scalers[pos] = joblib.load(scaler_path)

        feature_path = f'{path}/feature_columns.txt'

        if os.path.exists(feature_path):
            with open(feature_path, 'r') as file:
                for line in file:
                    if ': ' in line:
                        pos, cols = line.strip().split(': ')
                        self.feature_columns[pos] = cols.split(',')

        for pos in self.models:
            expected_features = self.POSITION_FEATURES.get(pos)
            if self.feature_columns.get(pos) != expected_features:
                raise ValueError(f"Saved {pos} model uses an outdated feature schema")



