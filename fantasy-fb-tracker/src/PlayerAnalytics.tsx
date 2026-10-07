import { ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useEffect, useState } from 'react'

type AnalyticsPoint = {
    week: number;
    actual?: number | null;
    espn_projection?: number | null;
    ml_projection?: number | null;
    lower_bound?: number | null;
    upper_bound?: number | null;
    preferred_projection?: number | null;
    preferred_source?: string;
    bye?: boolean;
    opponent?: string | null;
};

type ProjectionComparison = {
    weeks_evaluated: number;
    minimum_sample: number;
    espn_mae: number | null;
    ml_mae: number | null;
    selected_source: 'ESPN' | 'ML';
    selection_reason: string;
};

type DataSource = 'recent_games' | 'espn_fallback' | 'model' | 'unavailable';

type PlayerAnalyticsData = {
    player_name: string;
    position: string;
    team: string;
    current_week: number;
    recent_average: number | null;
    current_projection: number | null;
    current_selected_source: 'ESPN' | 'ML' | 'unavailable';
    current_espn_projection: number | null;
    current_ml_projection: number | null;
    confidence: number | null;
    data_source?: DataSource;
    history: AnalyticsPoint[];
    projection_comparison: ProjectionComparison;
    future_forecast: AnalyticsPoint[]
};

type Props = {
    playerId: number;
};

const API_BASE = 'http://localhost:5000';

const DATA_SOURCE_LABELS: Record<DataSource, { label: string; tone: 'good' | 'warning' | 'bad' }> = {
    recent_games: { label: 'ML projection selected', tone: 'good' },
    model: { label: 'ML projection selected', tone: 'good' },
    espn_fallback: { label: 'ESPN remains selected until ML proves more accurate', tone: 'warning' },
    unavailable: { label: 'No projection available', tone: 'bad' },
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

    const chartData = Array.from({ length: 18 }, (_, i) => {
        const week = i + 1;
        const h = data.history.find(p => p.week === week);
        const f = data.future_forecast.find(p => p.week === week);
        return {
            week,
            actual: h?.actual ?? null,
            espn_projection: h?.espn_projection ?? f?.espn_projection ?? null,
            ml_projection: h?.ml_projection ?? f?.ml_projection ?? null,
            range: f?.lower_bound != null && f?.upper_bound != null
                ? [f.lower_bound, f.upper_bound]
                : null,
        };
    });

    const chartMax = Math.ceil(Math.max(
        ...chartData.flatMap(d => [d.actual ?? 0, d.espn_projection ?? 0, d.ml_projection ?? 0, ...(d.range ?? [])])
    ) / 10) * 10;
    const savedPlayerEvaluations = data.history.filter(point =>
        point.espn_projection != null
        && point.ml_projection != null
        && point.actual != null
    );

    return (
        <div className="player-analytics">
            <div className="analytics-heading">
                <div>
                    <span className="analytics-eyebrow">PLAYER ANALYTICS</span>
                    <h2>{data.player_name}</h2>
                    <p>
                        <span className="analytics-player-tag">{data.position}</span>
                        <span className="analytics-player-tag">{data.team}</span>
                        <span className="analytics-week-label">Week {data.current_week}</span>
                    </p>
                </div>
                <div className={`analytics-selected analytics-selected--${data.current_selected_source.toLowerCase()}`}>
                    <span>Recommended projection</span>
                    <strong>{data.current_projection?.toFixed(1) ?? 'N/A'} <small>pts</small></strong>
                    <span>{data.current_selected_source === 'unavailable'
                        ? 'No projection available'
                        : `${data.current_selected_source} selected`}</span>
                </div>
            </div>

            <div className="analytics-summary">
                <div>
                    <span>Recent average</span>
                    <strong>{data.recent_average?.toFixed(1) ?? 'N/A'} <small>pts</small></strong>
                </div>

                <div>
                    <span>ESPN projection</span>
                    <strong>{data.current_espn_projection?.toFixed(1) ?? 'N/A'} <small>pts</small></strong>
                </div>

                <div>
                    <span>ML projection</span>
                    <strong>{data.current_ml_projection?.toFixed(1) ?? 'N/A'} <small>pts</small></strong>
                </div>

                <div>
                    <span>Model confidence</span>
                    <strong>{data.confidence != null ? `${Math.round(data.confidence * 100)}%` : 'N/A'}</strong>
                </div>
            </div>

            {sourceInfo && (
                <div className={`data-source-badge data-source-badge--${sourceInfo.tone} analytics-source-note`}>
                    {sourceInfo.label}
                </div>
            )}

            <div className="chart-panel">
                <div className="analytics-section-heading">
                    <div>
                        <span className="analytics-eyebrow">SEASON AT A GLANCE</span>
                        <h3>Scores & projections</h3>
                    </div>
                    <p>Weekly points</p>
                </div>

                <ResponsiveContainer width="100%" height={320}>
                    <ComposedChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis 
                            dataKey="week"
                            type="number"
                            domain={[1, 18]}
                            ticks={[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18]}
                            tickLine={false}
                            axisLine={false}
                        />
                        <YAxis domain={[0, chartMax || 10]} allowDataOverflow tickLine={false} axisLine={false} />
                        <Tooltip
                            labelFormatter={week => `Week ${week}`}
                            formatter={(value, name) => [
                                typeof value === 'number' ? `${value.toFixed(1)} pts` : '—',
                                name,
                            ]}
                            contentStyle={{ borderRadius: 10, border: '1px solid #e2e8f0', boxShadow: '0 8px 24px rgba(15, 23, 42, 0.12)' }}
                        />
                        <Legend verticalAlign="top" height={36} />

                        <Area
                            dataKey="range"
                            stroke="none"
                            fill="#94a3b8"
                            fillOpacity={0.16}
                            name="ML range"
                        />

                        <Line
                            dataKey="actual"
                            stroke="#0f766e"
                            strokeWidth={3}
                            dot={{ r: 3, fill: '#0f766e', strokeWidth: 0 }}
                            activeDot={{ r: 5 }}
                            name="Actual"
                            connectNulls
                        />

                        <Line
                            dataKey="espn_projection"
                            stroke="#64748b"
                            strokeDasharray="6 5"
                            strokeWidth={2}
                            dot={false}
                            name="ESPN"
                            connectNulls
                        />

                        <Line
                            dataKey="ml_projection"
                            stroke="#7c3aed"
                            strokeWidth={2.5}
                            dot={false}
                            name="ML"
                            connectNulls
                        />
                    </ComposedChart>
                </ResponsiveContainer>
            </div>

            <div className="forecast-table">
                <div className="analytics-section-heading">
                    <div>
                        <span className="analytics-eyebrow">REAL-WORLD TRACK RECORD</span>
                        <h3>Projection accuracy</h3>
                    </div>
                    <span className="analytics-position-tag">{data.position}</span>
                </div>
                <p className="analytics-note">
                    Uses saved forecasts from before kickoff. ESPN stays selected until ML is more accurate
                    across at least {data.projection_comparison.minimum_sample} player-weeks.
                </p>

                {data.projection_comparison.weeks_evaluated > 0 ? (
                    <>
                        <div className="accuracy-summary">
                            <div>
                                <span>Player-weeks</span>
                                <strong>{data.projection_comparison.weeks_evaluated}</strong>
                            </div>
                            <div>
                                <span>ESPN MAE</span>
                                <strong>{data.projection_comparison.espn_mae?.toFixed(2) ?? 'N/A'} pts</strong>
                            </div>
                            <div>
                                <span>ML MAE</span>
                                <strong>{data.projection_comparison.ml_mae?.toFixed(2) ?? 'N/A'} pts</strong>
                            </div>
                        </div>
                        <p className="analytics-note">
                            {data.projection_comparison.selection_reason}
                        </p>

                        <div className="analytics-table-scroll">
                        <table className="analytics-table">
                            <thead>
                                <tr>
                                    <th>Week</th>
                                    <th>ESPN</th>
                                    <th>ML</th>
                                    <th>Actual</th>
                                    <th>ESPN miss</th>
                                    <th>ML miss</th>
                                </tr>
                            </thead>
                            <tbody>
                                {savedPlayerEvaluations.map(point => (
                                    <tr key={`accuracy-${point.week}`}>
                                        <td>Week {point.week}</td>
                                        <td>{point.espn_projection?.toFixed(2)}</td>
                                        <td>{point.ml_projection?.toFixed(2)}</td>
                                        <td>{point.actual?.toFixed(2)}</td>
                                        <td>{Math.abs(point.espn_projection! - point.actual!).toFixed(2)}</td>
                                        <td>{Math.abs(point.ml_projection! - point.actual!).toFixed(2)}</td>
                                    </tr>
                                ))}
                                {savedPlayerEvaluations.length === 0 && (
                                    <tr>
                                        <td colSpan={6}>No saved projection snapshots for this player yet.</td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                        </div>
                    </>
                ) : (
                    <div className="analytics-empty">
                        <strong>Accuracy tracking is just getting started</strong>
                        <span>Once saved pre-game projections have actual scores, the comparison will appear here.</span>
                    </div>
                )}
            </div>

            <div className="forecast-table">
                <div className="analytics-section-heading">
                    <div>
                        <span className="analytics-eyebrow">UPCOMING MATCHUPS</span>
                        <h3>Remaining season</h3>
                    </div>
                    <span className="analytics-position-tag">{data.future_forecast.length} weeks</span>
                </div>

                <div className="analytics-table-scroll">
                <table className="analytics-table forecast-analytics-table">
                    <thead>
                        <tr>
                            <th>Week</th>
                            <th>Opponent</th>
                            <th>ESPN</th>
                            <th>ML</th>
                            <th>Recommended</th>
                            <th>ML range</th>
                        </tr>
                    </thead>

                    <tbody>
                        {data.future_forecast.map(point => (
                            <tr key={point.week}>
                                <td><strong>Week {point.week}</strong></td>
                                <td>{point.bye ? <span className="analytics-bye">BYE</span> : point.opponent ?? '—'}</td>
                                <td>{point.espn_projection?.toFixed(1) ?? '—'}</td>
                                <td>{point.ml_projection?.toFixed(1) ?? '—'}</td>
                                <td className="analytics-recommendation">
                                    {point.bye ? 'BYE' : (
                                        <>
                                            <strong>{point.preferred_projection?.toFixed(1) ?? '—'}</strong>
                                            <span>{point.preferred_source ?? 'N/A'}</span>
                                        </>
                                    )}
                                </td>
                                <td className="analytics-range">
                                    {point.lower_bound != null && point.upper_bound != null
                                        ? `${point.lower_bound.toFixed(1)}–${point.upper_bound.toFixed(1)}`
                                        : '—'}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                </div>
            </div>
        </div>
    );
}