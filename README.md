# Fantasy Football Tracker

## Idea
- Create a webiste that consolidates important information from you ESPN Fantasy Football League

## Note
- This uses a free open source ESPN API
- You can find it here: [https://github.com/cwendt94/espn-api](https://github.com/cwendt94/espn-api)

## Tech Stack
- React + TypeScript (Vite)
- Python backend

## Features
- Displays current league standings
- Displays the current weeks matchups
- Can display a rosters of the teams in your league

## Set Up
1. clone the repo (git clone https://github.com/RyanJordan817/fantasy-fb-tracker)
2. cd fantasy-fb-tracker
3. Run `npm install`
4. Add your league credentials to `.env` (LEAGUE_ID, YEAR, ESPN_S2, and SWID)
5. Run `npm run dev:all`

# Status
**Working features:** Displays of leageus overall standings, weekly matchups, and rosters

**Comming Soon:** Live score tracking, indepth player stat tacker and projections.