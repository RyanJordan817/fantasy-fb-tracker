import { LineChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useEffect, useState } from 'react'

type AnalyticsPoint = {
    week: number;
    actual?: number;
    espn_projection?: number | null;
    ml_projection?: number;
    lower_bound?: number;
    upper_bound?: number;
};

type PlayerAnalyticsData = {
    player_name: string;
    position: string;
    team: string;
    current_week: number;
    recent_average: number;
    current_projection: number;
    confidence: number;
    history: AnalyticsPoint[];
    future_forecast: AnalyticsPoint[]
};

type Props = {
    playerId: number;
};

const API_BASE = 'http://localhost:5000';

export default function PlayerAnalytics({ playerId }: Props) {
    const [data, setData] = useState<PlayerAnalyticsData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;

        async function loadAnalytics() {
            try {
                setLoading(true);

                const res = await fetch(`${API_BASE}/analytics/player/${playerId}`);
                if (!res.ok) throw new Error(`Unable to laod player analytics`);

                const data = await res.json();
                if (!cancelled) setData(data);

            } catch (requestError) {
                if (!cancelled) {
                    setError(requestError instanceof Error ? requestError.message : 'Unable to load analytics');

                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        }

        loadAnalytics();

        return () => {
            cancelled = true;
        };
    }, [playerId]);

    if (loading) {
        return <div className="analytics-loading">Loading analytics...</div>;
    }

    if (error || !data) {
        return (
            <div className="analytics-error">
                {error || 'No analytics avaliable'}
            </div>
        );
    }

    const chartData = [
        ...data.history.map(point => ({
            ...point,
            phase: 'Actual'
        })),
        ...data.future_forecast.map(point => ({
            ...point,
            phase: 'Forecast'
        }))
    ];

    return (
        <div className="player-analytics">
            <div className="analytics-summary">
                <div>
                    <span>Recent average</span>
                    <strong>{data.recent_average.toFixed(2)}</strong>
                </div>

                <div>
                    <span>ML Projection</span>
                    <strong>{data.current_projection.toFixed(2)}</strong>
                </div>

                <div>
                    <span>Confidence</span>
                    <strong>{Math.round(data.confidence * 100)}%</strong>
                </div>
            </div>

            <div className="chart-panel">
                <h3>Actual Performance vs Forcast</h3>

                <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                            dataKey="week"
                            label ={{
                                value: "Week",
                                position: 'insideBottom',
                                offset: -5
                            }}
                        />
                        <YAxis />
                        <Tooltip />
                        <Legend />

                        <Area
                            type="monotone"
                            dataKey="upper_bound"
                            stroke="none"
                            fill="#f59e0b"
                            fillOpacity={0.12}
                            name="Forecast range"
                        />

                        <Line
                            type="monotone"
                            dataKey="actual"
                            stroke="#2563eb"
                            strokeWidth={3}
                            dot={{ r: 4 }}
                            name="Acutal"
                        />

                        <Line
                            type="monotone"
                            dataKey="espn_projection"
                            stroke="#64748b"
                            strokeDasharray="5 5"
                            name="ESPN Projection"
                        />

                         <Line
                            type="monotone"
                            dataKey="ml_projection"
                            stroke="#f59e0b"
                            strokeWidth={3}
                            name="ML Projection"
                        />
                    </LineChart>
                </ResponsiveContainer>
            </div>

            <div className="forecast-table">
                <h3>Remaining Season Forecast</h3>

                <table>
                    <thead>
                        <tr>
                            <th>Week</th>
                            <th>ML</th>
                            <th>Range</th>
                        </tr>
                    </thead>

                    <tbody>
                        {data.future_forecast.map(point => (
                            <tr key={point.week}>
                                <td>Week {point.week}</td>
                                <td>{point.ml_projection?.toFixed(2)}</td>
                                <td>
                                    {point.lower_bound?.toFixed(1)}
                                    {' - '}
                                    {point.upper_bound?.toFixed(1)}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}