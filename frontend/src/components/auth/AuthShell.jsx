import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import { Wordmark } from '../landing/Navbar';
import { API_BASE } from '../../api';
import '../../styles/landing-v2.css';
import '../../styles/pages.css';

// Login and register share this frame: the product's claim on the left, the form on the right.
export default function AuthShell({ title, subtitle, children }) {
    return (
        <div className="cf-auth">
            <aside className="cf-auth-side">
                <Link to="/" className="cf-auth-home" aria-label="Cognifin home"><Wordmark /></Link>
                <div>
                    <p className="cf-auth-title">Every answer points to its page.</p>
                    <p className="cf-auth-lead">
                        Sign in to keep your chats and upload a company&apos;s annual report to ask about it.
                    </p>
                </div>
                {/* A real answer from the index: HDFC Bank Annual Report 2023, p.216 */}
                <figure className="cf-auth-sample">
                    <blockquote>
                        HDFC Limited&apos;s amalgamation with HDFC Bank became effective on
                        <strong> 1 July 2023</strong> <span className="cf-auth-chip">p.216</span>
                    </blockquote>
                    <figcaption>HDFC Bank Annual Report 2023</figcaption>
                </figure>
            </aside>
            <main className="cf-auth-main">
                <div className="cf-auth-form">
                    <h1 className="cf-auth-heading">{title}</h1>
                    <p className="cf-auth-sub">{subtitle}</p>
                    <a className="cf-auth-google" href={`${API_BASE}/auth/login`}>
                        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
                            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                        </svg>
                        Continue with Google
                    </a>
                    <div className="cf-auth-or">or</div>
                    {children}
                </div>
            </main>
        </div>
    );
}

export function Field({ id, label, ...input }) {
    return (
        <div className="cf-auth-field">
            <label htmlFor={id}>{label}</label>
            <input id={id} className="cf-auth-input" {...input} />
        </div>
    );
}

export function PasswordField({ id, label, ...input }) {
    const [shown, setShown] = useState(false);
    return (
        <div className="cf-auth-field">
            <label htmlFor={id}>{label}</label>
            <div className="cf-auth-pw">
                <input id={id} className="cf-auth-input" type={shown ? 'text' : 'password'} {...input} />
                <button type="button" className="cf-auth-show" onClick={() => setShown((s) => !s)}
                    aria-label={shown ? 'Hide password' : 'Show password'} aria-pressed={shown}>
                    {shown ? 'Hide' : 'Show'}
                </button>
            </div>
        </div>
    );
}

export function AuthError({ children }) {
    if (!children) return null;
    return (
        <p className="cf-auth-error" role="alert">
            <AlertTriangle size={14} aria-hidden="true" /> <span>{children}</span>
        </p>
    );
}
