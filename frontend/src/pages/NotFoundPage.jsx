import { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import Navbar from '../components/landing/Navbar';
import Footer from '../components/landing/Footer';
import '../styles/landing-v2.css';
import '../styles/pages.css';

// Keep in sync with SUGGESTED in pages/ChatPage.jsx and SHOWCASE_QUESTIONS in backend/main.py.
const TRY = [
  "What was TCS's consolidated revenue from operations in FY2024?",
  "What was Hindustan Unilever's profit after tax in FY2025?",
];

export default function NotFoundPage() {
  const { pathname } = useLocation();

  useEffect(() => {
    const prev = document.title;
    document.title = 'Page not found · Cognifin';
    return () => { document.title = prev; };
  }, []);

  return (
    <div className="cf-landing">
      <Navbar />
      <main className="cf-section cf-nf">
        <div className="cf-nf-inner">
          <span className="cf-nf-code">404</span>
          <h1 className="cf-h2">This page isn&apos;t in the filings.</h1>
          <p>
            Nothing lives at <code>{pathname}</code>. It may have moved, or the link has a typo.
          </p>
          <div className="cf-nf-actions">
            <Link className="cf-btn cf-btn-solid" to="/chat">Ask a question</Link>
            <Link className="cf-btn cf-btn-ghost" to="/">Back to home</Link>
          </div>
          <div className="cf-nf-try">
            <p>Or try one of these:</p>
            <ul>
              {TRY.map((q) => (
                <li key={q}><Link className="cf-link" to={`/chat?q=${encodeURIComponent(q)}`}>{q}</Link></li>
              ))}
            </ul>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}
