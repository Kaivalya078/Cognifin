import { Link } from 'react-router-dom';
import { Wordmark } from './Navbar';
import '../../styles/landing-v2.css';

export default function Footer() {
    return (
        <footer className="cf-footer">
            <div className="cf-footer-inner">
                <Wordmark />
                <nav className="cf-footer-links" aria-label="Footer">
                    <Link to="/engineering">Engineering</Link>
                    <Link to="/privacy">Privacy</Link>
                    <a href="https://github.com/Kaivalya078/Cognifin" target="_blank" rel="noreferrer">GitHub</a>
                </nav>
                <p className="cf-footer-copy">© {new Date().getFullYear()} Cognifin</p>
            </div>
        </footer>
    );
}
