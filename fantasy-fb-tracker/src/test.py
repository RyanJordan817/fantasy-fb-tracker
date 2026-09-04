# espn_s2: AECA4eAWsApMvjerya574rV59Jyuue1hQx9ktjixl5S6Ii%2BAgvTeUTxMXgZyOkiOUmvrXlflNtttfYoR9dd8n1vLHd9KHnkjfFq%2Bv2s6L0Rr2Q6Mov4ivOO5AsZ2wXJZOm%2B2K1cgCExHU5lhl5WFVS9JgzVNk8bKXvSdQWHjg6m9iyrMaeEZu9cXcCqs8hwhB75dPlODyrfGz%2F1LsuW6%2BRS1ivl3Us%2BFr1y00i5AASOnbl3SAADZUMPFZWaarRJ8tvcil3I1D7zZXv2Yqurxmuv%2FlIcjCEKm0qOmBiEpps1SIbMUJPjRyR%2FOTGXiCKCAJzk%3D
# SWID: {334C3EFE-3EAB-4ED9-80C3-BB880D1C2C71}
# leagueId: 1783894862

from espn_api.football import League

league = League(
    league_id=1783894862,
    year=2026,
    espn_s2="AECA4eAWsApMvjerya574rV59Jyuue1hQx9ktjixl5S6Ii%2BAgvTeUTxMXgZyOkiOUmvrXlflNtttfYoR9dd8n1vLHd9KHnkjfFq%2Bv2s6L0Rr2Q6Mov4ivOO5AsZ2wXJZOm%2B2K1cgCExHU5lhl5WFVS9JgzVNk8bKXvSdQWHjg6m9iyrMaeEZu9cXcCqs8hwhB75dPlODyrfGz%2F1LsuW6%2BRS1ivl3Us%2BFr1y00i5AASOnbl3SAADZUMPFZWaarRJ8tvcil3I1D7zZXv2Yqurxmuv%2FlIcjCEKm0qOmBiEpps1SIbMUJPjRyR%2FOTGXiCKCAJzk%3D",
    swid="{334C3EFE-3EAB-4ED9-80C3-BB880D1C2C71}"
)

# Fetch cirrent standings
def get_standings(league):
    return league.standings()

# view current week's mathcups
def get_matchups(league):
    return league.scoreboard()

# Look at specific team roster
def get_team_roster(league, team_index):
    team = league.teams[team_index]
    return team.roster

if __name__ == "__main__":
    # get curr standings
    standings = get_standings(league)
    print("Current Standinds:")
    for team in standings:
        print(f"{team.team_name}: {team.wins}-{team.losses}-{team.ties}")

    # get weekly mathchups
    matchups = get_matchups(league)
    print("\nCurrent Week's Matchups:")
    for match in matchups:
        print(f"{match.home_team} ({match.home_score}) vs {match.away_team} ({match.away_score})")

    # get specific team roster
    team_idx = 0
    roster = get_team_roster(league, team_idx)
    print(f"\nRoster for {league.teams[team_idx].team_name}:")
    for player in roster:
        print(f"{player.name} - {player.position} - {player.proTeam}")