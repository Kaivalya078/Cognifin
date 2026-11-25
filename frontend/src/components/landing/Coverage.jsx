import { Link } from 'react-router-dom';
import { COMPANIES } from '../../data/companies';

export default function Coverage() {
    return (
        <section className="cf-section cf-block" aria-labelledby="cf-coverage-h">
            <h2 id="cf-coverage-h" className="cf-h2">{COMPANIES.length} NIFTY 50 companies covered</h2>
            <ul className="cf-tickers">
                {COMPANIES.map((s) => <li key={s}>{s}</li>)}
            </ul>
            <p className="cf-note">
                Company not listed? <Link to="/chat" className="cf-link">Upload its annual report in the app.</Link>
            </p>
        </section>
    );
}
