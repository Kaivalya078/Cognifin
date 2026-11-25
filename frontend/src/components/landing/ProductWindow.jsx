import { PRODUCT_CASE as P } from '../../data/examples';

const fmt = (n) => n.toLocaleString('en-IN');

function Sparkline({ rows }) {
    const vals = rows.map((r) => r.value);
    const lo = Math.min(...vals) * 0.96;
    const hi = Math.max(...vals) * 1.02;
    const x = (i) => 34 + (i * 232) / (rows.length - 1);  // inset so end labels aren't clipped
    const y = (v) => 82 - ((v - lo) / (hi - lo)) * 66;
    const pts = rows.map((r, i) => `${x(i)},${y(r.value)}`).join(' ');
    return (
        <svg className="cf-spark" viewBox="0 0 300 112" aria-hidden="true" focusable="false">
            <line x1="0" y1="90" x2="300" y2="90" className="cf-spark-axis" />
            <polyline points={pts} className="cf-spark-line" />
            {rows.map((r, i) => (
                <g key={r.quarter}>
                    <circle cx={x(i)} cy={y(r.value)} r="3" className="cf-spark-dot" />
                    <text x={x(i)} y="106" textAnchor="middle" className="cf-spark-label">{r.quarter}</text>
                </g>
            ))}
        </svg>
    );
}

export default function ProductWindow() {
    const last = P.rows[P.rows.length - 1];
    const first = P.rows[0];
    const peak = P.rows.reduce((a, b) => (b.value > a.value ? b : a));
    return (
        <section id="product" className="cf-section cf-block">
            <h2 className="cf-h2">See the source, not just the answer.</h2>
            <p className="cf-lead">
                Answers come with page chips you can open, and figures are drawn from a table of
                results checked against the filings.
            </p>
            <figure className="cf-window" aria-label="Example answer with its verified figures">
                <div className="cf-window-chat">
                    <p className="cf-window-q">{P.question}</p>
                    <p className="cf-window-a">
                        Infosys&apos;s consolidated net profit was <b>₹{fmt(last.value)} crore</b> in {last.quarter},
                        against <b>₹{fmt(first.value)} crore</b> in {first.quarter} <span className="cf-chip">table</span>.
                        The highest of the four was <b>₹{fmt(peak.value)} crore</b> in {peak.quarter}{' '}
                        <span className="cf-chip">table</span>.
                    </p>
                    <Sparkline rows={P.rows} />
                </div>
                <div className="cf-window-source">
                    <table className="cf-window-table">
                        <caption className="cf-window-source-head">Verified figures · INFY consolidated net profit</caption>
                        <thead>
                            <tr><th scope="col">Quarter</th><th scope="col">₹ crore</th><th scope="col">Source</th></tr>
                        </thead>
                        <tbody>
                            {P.rows.map((r) => (
                                <tr key={r.quarter} className={r === last ? 'is-hit' : undefined}>
                                    <th scope="row">{r.quarter}</th>
                                    <td>{fmt(r.value)}</td>
                                    <td>{r.source}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </figure>
        </section>
    );
}
