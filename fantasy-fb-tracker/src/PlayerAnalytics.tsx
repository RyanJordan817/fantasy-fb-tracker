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

type MLEvaluation = {
    weeks_evaluated: number;
    mean_absolute_error: number | null;
    average_error: number | null;
};

type DataSource = 'recent_games' | 'positional_fallabck' | 'espn_fallback' | 'model' | 'unavaliable';

type PlayerAnalyticsData = {
    player_name: string;
    position: string;
    team: string;
    current_week: number;
    recent_average: number;
    current_projection: number;
    confidence: number;
    data_source?: DataSource;
    history: AnalyticsPoint[];
    ml_evaluation: MLEvaluation;
    future_forecast: AnalyticsPoint[]
};

type Props = {
    playerId: number;
};

const API_BASE = 'http://localhost:5000';

const DATA_SOURCE_LABELS: Record<DataSource, { label: string; tone: 'good' | 'warning' | 'bad' }> = {
    recent_games: { label: 'Based on recent game data (ML)', tone: 'good' },
    model: { label: 'Based on recent game data (Model)', tone: 'good' },
    positional_fallabck: { label: 'Limited data \u2026 using positional average', tone: 'warning'} ,
    espn_fallback: { label: 'ML unavalible \u2026 showing ESPN projection', tone: 'warning' },
    unavaliable: { label: 'Projection unavaliable', tone: 'bad' },
};

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

    const sourceInfo = data.data_source ? DATA_SOURCE_LABELS[data.data_source] : null;

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

    const forecastMax = Math.max(
        ...data.future_forecast.map(point => point.upper_bound ?? point.ml_projection ?? 0),
        0
    );
    const chartMax = Math.max(30, Math.ceil((forecastMax * 1.2) / 5) * 5);

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

            {sourceInfo && (
                <div className={`data-source-badge data-source-badge--${sourceInfo.tone}`}>
                    {sourceInfo.label}
                </div>
            )};

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
                        <YAxis domain={[0, chartMax]} allowDataOverflow />
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
                <h3>ML Accuracy So Far</h3>
                <p className="analytics-note">
                    Positive difference means the ML projection was higher than the actual score.
                </p>

                {data.ml_evaluation.weeks_evaluated > 0 ? (
                    <>
                        <div className="accuracy-summary">
                            <div>
                                <span>Weeks tested</span>
                                <strong>{data.ml_evaluation.weeks_evaluated}</strong>
                            </div>
                            <div>
                                <span>Avg. miss</span>
                                <strong>{data.ml_evaluation.mean_absolute_error?.toFixed(2)} pts</strong>
                            </div>
                            <div>
                                <span>Avg. error</span>
                                <strong>{data.ml_evaluation.average_error?.toFixed(2)} pts</strong>
                            </div>
                        </div>

                        <table>
                            <thead>
                                <tr>
                                    <th>Week</th>
                                    <th>ML</th>
                                    <th>Actual</th>
                                    <th>Difference</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.history.filter(point => point.ml_projection !== undefined).map(point => (
                                    <tr key={`accuracy-${point.week}`}>
                                        <td>Week {point.week}</td>
                                        <td>{point.ml_projection?.toFixed(2)}</td>
                                        <td>{point.actual?.toFixed(2)}</td>
                                        <td>{(point.ml_projection! - (point.actual ?? 0)).toFixed(2)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </>
                ) : (
                    <p className="analytics-note">No completed weeks are available for testing yet.</p>
                )}
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