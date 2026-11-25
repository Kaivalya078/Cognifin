import {
    Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

// Verified figures from the financials table. Every point is a table row; clicking
// one opens the filing it came from (BSE PDF at its page, or the NSE iXBRL page).
const COLORS = ['#c9a24a', '#8fa8c8', '#7fb08a', '#c98a7a', '#a99ac4', '#e0c98a'];
const fmt = (v) => (typeof v === 'number' ? v.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : v);

function openSource(pt) {
    if (!pt?.source_url) return;
    const isPdf = /\.pdf($|\?)/i.test(pt.source_url);
    window.open(pt.source_url + (isPdf && pt.page ? `#page=${pt.page}` : ''), '_blank', 'noopener');
}

const tooltipStyle = {
    background: 'var(--cf-bg-raised)', border: '1px solid var(--cf-gold-line)', borderRadius: 8,
    color: 'var(--cf-ink)', fontSize: 12,
};
const axis = { fill: 'var(--cf-sub)', fontSize: 11 };

export default function FinancialChart({ chart, numbersCheck }) {
    if (!chart?.series?.length) return null;
    const { series, display_unit: unit } = chart;
    const singlePeriod = series.every((s) => s.points.length === 1);
    const unmatched = numbersCheck?.unmatched || [];
    const title = `${chart.title || series[0].label} (${unit})`;

    let body;
    if (singlePeriod) {
        const data = series.map((s) => ({ name: s.name, value: s.points[0].value, pt: s.points[0] }));
        body = (
            <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
                <CartesianGrid stroke="var(--cf-line)" vertical={false} />
                <XAxis dataKey="name" tick={axis} stroke="var(--cf-line)" interval={0} />
                <YAxis tick={axis} stroke="var(--cf-line)" tickFormatter={fmt} width={64} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'var(--cf-gold-soft)' }}
                    formatter={(v, _n, item) => [`${fmt(v)} ${unit}, ${item.payload.pt.label}, ${item.payload.pt.method}`, item.payload.name]} />
                <Bar dataKey="value" cursor="pointer" onClick={(d) => openSource(d?.payload?.pt)}>
                    {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Bar>
            </BarChart>
        );
    } else {
        // One row per period; each series contributes its value and its point (for click/tooltip).
        const rows = new Map();
        series.forEach((s) => s.points.forEach((p) => {
            const row = rows.get(p.period_end) || { period_end: p.period_end, label: p.label };
            row[s.name] = p.value;
            row[`${s.name}__pt`] = p;
            rows.set(p.period_end, row);
        }));
        const data = [...rows.values()].sort((a, b) => a.period_end.localeCompare(b.period_end));
        body = (
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
                <CartesianGrid stroke="var(--cf-line)" vertical={false} />
                <XAxis dataKey="label" tick={axis} stroke="var(--cf-line)" />
                <YAxis tick={axis} stroke="var(--cf-line)" tickFormatter={fmt} width={64} />
                <Tooltip contentStyle={tooltipStyle}
                    formatter={(v, name, item) => [`${fmt(v)} ${unit}, ${item.payload[`${name}__pt`]?.method}`, name]} />
                {series.map((s, i) => (
                    <Line key={s.name} type="linear" dataKey={s.name} connectNulls
                        stroke={COLORS[i % COLORS.length]} strokeWidth={2}
                        dot={({ cx, cy, payload, key }) => (
                            <circle key={key} cx={cx} cy={cy} r={4} fill={COLORS[i % COLORS.length]}
                                style={{ cursor: 'pointer' }} onClick={() => openSource(payload[`${s.name}__pt`])} />
                        )} />
                ))}
            </LineChart>
        );
    }

    return (
        <div className="cx-chart">
            <div className="cx-chart-title">
                {title}{series.length > 1 && `: ${series.map((s) => s.name).join(' vs ')}`}
            </div>
            <ResponsiveContainer width="100%" height={260}>{body}</ResponsiveContainer>
            <div className="cx-chart-note">Verified figures from company filings. Click a point to open its filing.</div>
            {chart.mixed_basis && (
                <div className="cx-chart-note">Companies are shown on different bases (consolidated vs standalone), so they aren&apos;t directly comparable.</div>
            )}
            {unmatched.length > 0 && (
                <div className="cx-chart-note is-warn">
                    {unmatched.length} number{unmatched.length > 1 ? 's' : ''} in this answer didn&apos;t match the verified table: {unmatched.join(', ')}
                </div>
            )}
        </div>
    );
}
