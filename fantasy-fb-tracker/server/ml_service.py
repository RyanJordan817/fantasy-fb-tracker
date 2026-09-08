import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
import nflreadpy as nfl
import joblib
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

class NFLPlayerProjector:
    def __init__(self):
        self.models= {}
        self.scalers = {}
        self.feature_columns = []
        self.last_trained = None

    def fetch_historical_data(self, seasons=[2020, 2021, 2022, 2023, 2024]):
        """
        Historcal data for training
        """
        print(f"Fetching data for seasons: {seasons}")

        player_stats = nfl.import_seasonal_data(seasons)

        player_info = nfl.import_rosters(seasons)

        merged_data= pd.merge(
            player_stats,
            player_info[['player_id', 'postion', 'team']],
            on='player_id',
            how='left'
        )

        merged_data = self._engineer_features(merged_data)

        return merged_data

    def _engineer_features(self, df):
        """
        Create advanced features for better predictions
        """

        # Create featur columns
        df['fantasy_points'] = df['passing_yds']*0.04 + df['passing_td']*4 + \
                                df['rushin_yds']*0.01 + df['rushing_td']*6 + \
                                df['receiving_yds']*0.1 + df['receiving_td']*6 + \
                                df['receptions']*1

        # Add rolling averages 
        df['games_played'] = df.groupby('player_id')['game_id'].transform('count')

        # Calculate per-game avgs
        for stat in ['passing_yds', 'rushing_yds', 'receiving_yds', 'receptions', 'fantasy_points']:
            if stat in df.columns:
                df[f'avg_{stat}_last_5'] = df.groupby('player_id')[stat].transform(lambda x: x.rolling(5, min_periods=1).mean())

        if 'birth_date' in df.columns:
            df['age'] = 2026 - pd.to_datetime(df['birth_date']).dt.year

        return df

    def prepare_training_data(self, df, position):
        """
        Prepare features and targets for a specific position
        """

        pos_df = df[df['position'] == position].copy()

        # Define feature based on pos
        if position == 'QB':
            features = [
                'passing_yds', 'passing_td', 'passing_att', 'rushing_yds', 'rushing_td',
                'avg_passing_yds_last_5', 'avg_rushing_yds_last_5',
                'age' if 'age' in pos_df.columns else None
            ]
            target = 'fantasy_points'

        elif position in ['RB', 'WR', 'TE']:
            features = [
                'receptions', 'receiving_yds', 'receiving_td', 'rushing_yds', 'rushing_td',
                'avg_receiving_yds_last_5', 'avg_rushing_yds_last_5', 'avg_receptions_last_5',
                'age' if 'age' in pos_df.columns else None
            ]
            target = 'fantasy_points'

        else:
            return None, None

        features = [feat for feat in features if feat is not None]

        features = [feat for feat in features if feat in pos_df.columns]

        x = pos_df[features].dropna()
        y = pos_df.loc[x.index, target]

        return x, y

    def train_models(self, positions=['QB', 'RB', 'WR', 'TE'], seasons=[2020, 2021, 2022, 2023, 2024]):
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


    def predict_player(self, player, pos, team):
        """"
        Predict points for a single player
        """

        if pos not in self.models:
            print(f"No model trained for {pos}")
            return None

        features = self.feature_columns[pos]

        default_vals = {
            'passing_yds': 250,
            'passing_td': 2,
            'rushing_yds': 30,
            'rushing_td': 0.3,
            'receiving_yds': 50,
            'receiving_td': 0.4,
            'receptions': 5
        }

        feature_vector = []
        for feat in features:
            if feat in default_vals:
                feature_vector.append(default_vals[feat])
            else:
                feature_vector.append(0)

        x_scaled = self.scalers[pos].transform([feature_vector])
        prediction = self.models[pos].predict(x_scaled)[0]

        return round(prediction, 2)

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
            scaler_path = f'{path}/model_{pos}.pkl'

            if os.path.exists(model_path) and os.path.exists(scaler_path):
                self.models[pos] = joblib.load(model_path)
                self.scalers[pos] = joblib.load(scaler_path)

        if os.path.exists(f'{path}/feature_columns.txt'):
            with open(f'{path}/feature_clumns.txt', 'r') as f:
                for line in f:
                    if ': ' in line:
                        pos, cols = line.strip().split(': ')
                        self.feature_columns[pos] = cols.split(',')



