import { useEffect } from 'react';
import Navbar from '../components/landing/Navbar';
import Footer from '../components/landing/Footer';
import '../styles/landing-v2.css';
import '../styles/pages.css';

// Keep in sync with what the backend stores (backend/db.py, routers/conversations.py).
export default function PrivacyPage() {
  useEffect(() => {
    const prev = document.title;
    document.title = 'Privacy · Cognifin';
    return () => { document.title = prev; };
  }, []);

  return (
    <div className="cf-landing">
      <Navbar />
      <main className="cf-section cf-eng cf-privacy">
        <span className="cf-eng-eyebrow">Last updated 26 Nov 2026</span>
        <h1 className="cf-h1 cf-eng-title">Privacy</h1>
        <p>Cognifin is a personal portfolio project. It keeps as little about you as it can.</p>

        <h2>What is stored</h2>
        <ul>
          <li><strong>Account:</strong> if you sign in with Google, your name, email address and profile picture, plus when you signed up and last signed in. With email sign-up, your name, email and a hashed password.</li>
          <li><strong>Conversations:</strong> if you are signed in, your questions and Cognifin&apos;s answers are saved so you can reopen them. You can delete any conversation in the app.</li>
          <li><strong>Uploaded PDFs:</strong> held in server memory for about an hour for your session, then discarded. They are not written to disk or a database.</li>
        </ul>
        <p>Without signing in, nothing is saved to an account.</p>

        <h2>Who processes it</h2>
        <ul>
          <li>Your questions and the relevant filing excerpts are sent to an AI model provider (OpenAI) to write the answer.</li>
          <li>Account and conversation data lives in a MongoDB Atlas database. The app runs on Microsoft Azure and Vercel.</li>
        </ul>
        <p>Nothing is sold or shared for advertising. There are no analytics or tracking cookies; your sign-in token stays in your browser&apos;s local storage.</p>

        <h2>Deleting your data</h2>
        <p>
          To delete your account and everything linked to it, open an issue on{' '}
          <a className="cf-link" href="https://github.com/Kaivalya078/Cognifin/issues" target="_blank" rel="noreferrer">GitHub</a>.
        </p>

        <p>Cognifin answers from public company filings. It is not financial advice.</p>
      </main>
      <Footer />
    </div>
  );
}
