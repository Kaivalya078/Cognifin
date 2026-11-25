import { Link } from 'react-router-dom';
import { proofItems } from '../../utils/landing';

export default function Proof({ metrics }) {
    const items = proofItems(metrics);
    if (!items) return null;
    return (
        <section className="cf-section cf-block" aria-labelledby="cf-proof-h">
            <h2 id="cf-proof-h" className="cf-h2">Measured, not claimed.</h2>
            <dl className="cf-proof">
                {items.map((it) => (
                    <div key={it.label} className="cf-proof-item">
                        <dt className="cf-proof-label">{it.label}</dt>
                        <dd className="cf-proof-value">{it.value}</dd>
                    </div>
                ))}
            </dl>
            <Link to="/engineering" className="cf-link">How it&apos;s measured</Link>
        </section>
    );
}
