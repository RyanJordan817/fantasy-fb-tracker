import React, { useEffect, useState } from 'react'

interface Projections {
    player_name: string;
    position: string;
    team: string;
    projected_points: number;
    pro_team: string;
    injury_status: string;
    percent_owned: number;
}

const Projections: React.FC = () => {
    const [projections, setProjections] = useState<Projections[]>([]);
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null);
    const [filter, setFilter] = useState<string>('All');

    const API_BASE = 'http://localhost:5000'
    
    useEffect(() => {
        fetchProjections();
    }, []);

    const fetchProjections= async () => {
        try {
            const res = await fetch(`${API_BASE}/projections/weekly`);
            if (!res.ok) throw new Error(`Railed to fetch projections`);

            const data = await res.json();
            setProjections(data);

        } catch(error) {
            console.error(`Failed to load projections`);
            setError(error instanceof Error ? error.message : 'Failed to load projections');
        } finally {
            setLoading(false)
        }
    };

    const positions = ['ALL', 'QB', 'RB', 'TE', 'WR'];
    const filteredProjections = filter === 'ALL' ? projections : projections.filter(p => p.position === filter);

    if (loading) return <div className="loading">Loading projections...</div>;
    if (error) return <div className="error">{error}</div>;

    return (
        <div className="projections-container">
            <div className="section-header">
                <h2>Weekly Projections</h2>
                <div className="filter-buttons">
                    {positions.map(pos => (
                        <button 
                            key={pos}
                            className={`filter-btn ${filter === pos ? 'active' : ''}`}
                            onClick={() => setFilter(pos)}
                        >
                            {pos}
                        </button>
                    ))}
                </div>
            </div>

            <div className="projections-grid">
                {filteredProjections.slice(0, 50).map((player, idx) => (
                    <div key={idx} className="projection-card">
                        <div className="rank">{idx + 1}</div>
                        <div className="player-info">
                            <div className="player-name">{player.player_name}</div>
                            <div className="position-detials">
                                <span className="position-badge">{player.position}</span>
                                <span className="team">{player.pro_team}</span>
                                {player.injury_status && player.injury_status !== 'Healthy' && (
                                    <span className="injury-badge">{player.injury_status}</span>
                                )}
                            </div>
                        </div>
                        <div className="projected-points">
                            <span className="points">{player.projected_points?.toFixed(2) || 'N/A'}</span>
                            <span className="points-label">pts</span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default Projections;
