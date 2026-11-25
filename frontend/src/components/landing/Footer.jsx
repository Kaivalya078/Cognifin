import { Link } from 'react-router-dom';
import './../../styles/landing.css';

export default function Footer() {
    const currentYear = new Date().getFullYear();

    return (
        <footer className="landing-footer">
            <div className="footer-container">
                {/* Logo & Description */}
                <div className="footer-brand">
                    <div className="footer-logo">
                        <span className="logo-icon">◈</span>
                        <span className="logo-text">Cognifin</span>
                    </div>
                    <p className="footer-tagline">
                        Unlock financial intelligence with AI-powered document analysis
                    </p>
                </div>

                {/* Partner Logos */}
                <div className="footer-partners">
                    <span className="partners-label">Powered by</span>
                    <div className="partners-list">
                        <span className="partner-item">OpenAI</span>
                        <span className="partner-item">LanceDB</span>
                        <span className="partner-item">React</span>
                        <span className="partner-item">FastAPI</span>
                    </div>
                </div>

                {/* Copyright */}
                <div className="footer-copyright">
                    <p>© {currentYear} Cognifin. Built for financial analysis. <Link to="/engineering" className="footer-link">How it's measured</Link></p>
                </div>
            </div>
        </footer>
    );
}
