import React, { useEffect, useState } from 'react'
import './style.css'

type Standings ={
    team_id: number;
    team_name: string;
    team_abbrev: string;
    wins: number;
    losses: number;
    ties: number;
    points_for: number;
    points_against: number;
    waiver_rank: number;
    acquisitions: number;
    drops: number;
    trades: number;
    owners: string;  //array of owners (though one for my league)
    stats: string;
    streak_type: string;
    streak_length: number;
    standing: number;
    final_standing: number;
    draft_projected_rank: number;
    playoff_pct: number;
}

type Matchup = {
    home_team: string;
    home_score: number;
    home_prodj: number;
    away_team: string;
    away_score: number;
    away_prodj: number;
    is_playoff: boolean;
    match_type: string;
}

type Roster = {
    name: string;
    pos_rank: number;
    pro_team: string;
    lineup_pos: string;
    acquisition_type: string;
    position: string;
    injury_status: string;
    is_injured: boolean;
    total_points: number;
    avg_points: number;
    prodj_total_pts: number;
    prodj_avg_pts: number;
    percent_owned: number;
    percent_start: number;
    stats: string;
}

type Teams = {
    name: string;
    team_id: number;
}

function App() {
    const [standings, setStandings] = useState<Standings[] | null>(null);
    const [matchups, setMatchups] = useState<Matchup[] | null>(null);
    const [roster, setRoster] = useState<Roster[] | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedTeamId, setSelectedTeamId] = useState<number>(1);
    const [rosterLoading, setRosterLoading] = useState(false);
    const [teams, setTeams] = useState<Teams[] | null>(null);

    const API_BASE = 'http://localhost:5000';

    useEffect(() => {
        fetchAllData();
    }, []);

    const fetchAllData = async () => {
        setLoading(true);
        setError(null);
        try {
            await fetchStandings();
            await fetchMatchups();
            await fetchTeams();
        } catch (error) {
            console.error('Error fetching data:', error)
        }
        setLoading(false);
    }

    const fetchStandings = async () => {
            try {
                const res = await fetch(`${API_BASE}/standings`);
                if (!res.ok) throw new Error (`HTTP Error! status: ${res.status}`);

                const data = await res.json();
                console.log('Standings:', data);
                console.log('Standings:', data);
                console.log('📊 Team IDs:', data.map((t: Standings) => ({ id: t.team_id, name: t.team_name })));
                setStandings(data);
            } catch (error) {
                console.error('Error fetching standings:', error);
                setError('Failed to load stadings');
            }
        };

    const fetchMatchups = async () => {
        try {
            const res = await fetch(`${API_BASE}/matchups`);
            if (!res.ok) throw new Error (`HTTP Error! status: ${res.status}`);

            const data = await res.json();
            console.log('Matchups:', data);
            setMatchups(data);
        } catch (error) {
            console.error('Error fetching mathcups:', error);
            setError('Failed to load mautchups');
        }
    };

    const fetchRoster = async (team_id: number) => {
        setRosterLoading(true);
        setError(null);
        try {
            const res = await fetch(`${API_BASE}/team/${team_id}/roster`);
            if (!res.ok) throw new Error (`HTTP Error! Status: ${res.status}`);

            const data = await res.json();
            console.log('Roster for team:', team_id, ':', data);
            setRoster(data);
        } catch (error) {
            console.error(`Error fecthing roster for team ${team_id}:`, error);
            const teamName = teams?.[team_id]?.name || `Team ${team_id}`;
            setError(`Failed to load roster for team ${teamName}`);
            setRoster(null);
        } finally {
            setRosterLoading(false);
        }
    };

    // Allows for picking a different team roster
    const handleTeamChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        const team_id = parseInt(event.target.value);
        setSelectedTeamId(team_id);
        fetchRoster(team_id);
    }

    const fetchTeams = async () => {
        try {
            const res = await fetch(`${API_BASE}/teams`);
            if (!res.ok) throw new Error (`HTTP Error! status: ${res.status}`)

            const data = await res.json();
            console.log('Teams:', data);
            setTeams(data);

            if (data && data.length > 0) {
                const firstTeamId = data[0].team_id;
                setSelectedTeamId(firstTeamId);
                await fetchRoster(firstTeamId);
            }
        } catch (error) {
            console.log(`Failed to fetch teams:`, error);
            setError('Failed to load teams');
        }
    }

    // Loading State
    if (loading) {
        return (
            <div className="app">
                <header className="app-header">
                    <h1>Fantasy Football Tracker</h1>
                    <div className="subtitle"> 2026 Season</div>
                </header>
                <div className="loading">
                    <div className="loading-spinner"></div>
                    <p>Loading Fantasy Data</p>
                </div>
            </div>
        );
    }

    // Error State
    if (error && !rosterLoading) {
        return (
            <div className="app">
                <header className="app-header">
                    <h1>🏈 Fantasy Football Tracker</h1>
                    <div className="subtitle">2026 Season</div>
                </header>
                <div className="error">
                    <p>⚠️ {error} </p>
                    <button onClick={fetchAllData}>Retry</button>
                </div>
            </div>
        );
    }

	return (
        <div className="app">
            <header className="app-header">
                <h1>Fantasy Football Tracker</h1>
                <div className="subtitle">2026 Season</div>
            </header>

            {/* Standings Section */}
            <div className="section-container">
                <div className="section-header">
                    Current Standings:
                    <span className="badge">{standings?.length || 0} Teams</span>
                </div>

                <table className="standings-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Team</th>
                            <th style={{ textAlign: 'center'}}>Record</th>
                            <th style={{ textAlign: 'right' }}>Points</th>
                        </tr>
                    </thead>
                    <tbody>
                        {standings ? (
                            standings.map((team, index) => (
                                <tr key={index}> 
                                    <td className={`rank ${index === 0 ? 'gold' : index === 1 ? 'silver' : index == 2 ? 'bronze' : ''}`}>
                                        {index + 1}
                                    </td>
                                    <td className="team-name"> {team.team_name} </td>
                                    <td className="record">
                                        <span className="wins">{team.wins}W</span>
                                        <span style={{ margin: '0 4px', color: '#9ca3af' }}>:</span>
                                        <span className="losses">{team.losses}L</span>
                                    </td>
                                    <td style={{ textAlign: 'right', fontWeight: '600' }}>
                                        {team.points_for?.toFixed(1) || '-'}
                                    </td>
                                </tr>
                            ))
                        ) : ( 
                            <tr>
                                <td colSpan={4} style={{ textAlign: 'center', padding: '20px', color: '#6b7280'}}>
                                    No Standings Avaliable
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>

                {/* Matchups Section */}
                <div className="section-container">
                    <div className="section-header">
                        This Weeks Matchups:
                        <span className="badge">{matchups?.length || 0} Games</span>
                    </div>

                    <div className="matchups-grid">
                        {matchups ? (
                            matchups.map((match, idx) => (
                                <div key={idx} className="matchup-card">
                                    <div className="team">
                                        <span className="team-name">{match.home_team}</span>
                                        <span className={`team-score ${match.home_prodj > match.away_prodj ? 'higher' : 'lower'}`}>
                                            {match.home_prodj.toFixed(2)}
                                        </span>
                                    </div>

                                    <span className="vs">VS</span>

                                    <div className="team">
                                        <span className="team-name">{match.away_team}</span>
                                        <span className={`team-score ${match.away_prodj > match.home_prodj ? 'higher' : 'lower'}`}>
                                            {match.away_prodj.toFixed(2)}
                                        </span>
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '20px', color: '#6b7280'}}>
                                No matchup Data Avaliable
                            </div>
                        )}
                    </div>
                </div>

                {/* Roster Section */}
                <div className="section-container">
                    <div className="section-header">
                        Team Roster:
                        <span className="badge">{roster?.length || 0} Players</span>
                        
                        {/* Team Selector Dropdwon */}
                        <select
                            className="team-selector"
                            value={selectedTeamId || ''}
                            onChange={handleTeamChange}
                        >
                            {teams?.map((team) => (
                                <option key={team.team_id} value={team.team_id}>
                                    {team.name}
                                </option>
                            ))}
                        </select>
                    </div>

                    {rosterLoading ? (
                        <div style={{ textAlign: 'center', padding: '40px' }}>
                            <div className="loading=spinner"></div>
                            <p style={{ color: '#6b7280', marginTop: '12px'}}>Loading Roster...</p>
                        </div>
                    ) : (
                        <div className="roster-grid">
                                {roster && roster.length > 0 ? (
                                    roster.map((player, idx) => (
                                        <div key={`${player.name}-${idx}`} className="roster-card">
                                            <div className="player-name">{player.name}</div>
                                            <div className="player-details">
                                                <span className="player-position">{player.position}</span>
                                                {player.pos_rank > 0 && (
                                                    <span className="player-rank">#{player.pos_rank}</span>
                                                )}
                                                <span className="player-team">{player.pro_team}</span>
                                                {player.injury_status && player.injury_status !== 'Healthy' && (
                                                    <span className="injury-badge">{player.injury_status}</span>
                                                )}
                                            </div>
                                            <div className="player-stats">
                                                <span>Avg: {player.avg_points.toFixed(1)}</span>
                                                <span>Total: {player.total_points.toFixed(1)}</span>
                                            </div>
                                        </div>
                                    ))
                                ) : (
                                    <div style={{ textAlign: 'center', padding: '20px', color: '#6b7280' }}>
                                        No Roster Data Avaliable
                                    </div>
                                )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default App
