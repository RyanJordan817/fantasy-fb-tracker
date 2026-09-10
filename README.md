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
**Working features:** League standings, weekly matchups, team rosters, player detail modals, and weekly player projections.

**Coming Soon:** Live score tracking and more in-depth player analytics.