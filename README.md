# Fantasy Football Tracker

## Idea
- Fantasy Football Tracker is a web application that consolidates useful information from an ESPN Fantasy Football league in one dashboard. It combines league standings, weekly matchups, team rosters, player details, and weekly player projections.

## Note
- The backend uses the open-source `espn-api` Python package to retrieve ESPN Fantasy Football league data.
- The package is available at [https://github.com/cwendt94/espn-api](https://github.com/cwendt94/espn-api).
- The league must be accessible with the ESPN credentials configured in `.env`.

## Tech Stack
- React + TypeScript with Vite for the frontend
- Python + Flask for the backend API
- scikit-learn and NFL data from `nflreadpy` for player projections

## Features
- Displays current league standings, records, and points for
- Displays the current week's matchups and projected scores
- Lets you switch between teams and view their rosters
- Shows player position, NFL team, injury status, and fantasy statistics
- Opens additional player statistics and projected stat breakdowns
- Displays weekly player projections with QB, RB, WR, and TE filters
- Uses position-specific machine learning models when generating projections
- Trains against nflreadpy weekly player stats scored with the active ESPN league's scoring settings
- Includes a lagged historical defense-vs-position feature when generating ML projections
- Shows ESPN and ML projections side by side, with matchup context and forecast ranges
- Compares immutable forecasts saved before actual scores with completed player-week results
- Keeps ESPN as the selected projection until prospective ML results beat ESPN over at least 30 player-weeks for that position
- Loads week-by-week ESPN actual scores and projections for player analytics, with a local season cache
- Refreshes models idempotently as completed regular-season weeks advance, excluding the current/incomplete week
- Reports prospective ESPN and ML mean absolute error by position; weeks without saved forecasts are not backfilled into the comparison
- Scales the forecast chart to typical player scoring ranges and excludes ESPN season-level projections from weekly chart data
- Detects outdated saved model feature schemas or ESPN scoring rules and retrains models when necessary

## Set Up
1. Clone the repository: `git clone https://github.com/RyanJordan817/fantasy-fb-tracker`
2. Change into the project directory: `cd fantasy-fb-tracker/fantasy-fb-tracker`
3. Install the frontend dependencies: `npm install`
4. Create and activate a Python virtual environment.
5. Install the backend dependencies: `pip install flask flask-cors python-dotenv espn-api pandas numpy scikit-learn nflreadpy joblib`
6. Add your ESPN league credentials to `.env`: `LEAGUE_ID`, `YEAR`, `ESPN_S2`, and `SWID`.
7. Start the frontend and backend together: `npm run dev:all`
8. Open the Vite URL shown in the terminal, usually `http://localhost:5173`.

# Status
**Working features:** League standings, weekly matchups, team rosters, player detail modals, weekly player projections, player analytics, forecast ranges, and historical ML accuracy tracking.

**Projection evaluation:** ESPN and ML forecasts are saved the first time the current week's projections are observed while the player has no recorded actual score. Those saved forecasts are immutable and are compared with ESPN actuals only after the week is complete. Historical weeks without saved forecast snapshots are excluded rather than reconstructed using a model that may have seen their scores. ESPN remains the selected projection unless the position-level prospective sample has at least 30 player-weeks and ML has lower MAE. The metrics are evaluation statistics, not calibrated probabilities.

Players without available nflreadpy game history do not receive a fabricated positional-average prediction. The app shows an ESPN weekly projection when available, otherwise it reports that no projection is available.

**Coming Soon:** Live score tracking