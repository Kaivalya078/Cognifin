/**
 * Auth Callback Page
 * ===================
 * Handles the redirect from Google OAuth via the backend.
 * Extracts JWT token and user info from URL params,
 * stores them in localStorage, and redirects to /chat.
 */

import { useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { AlertTriangle } from 'lucide-react';
import { Wordmark } from '../components/landing/Navbar';
import '../styles/landing-v2.css';
import '../styles/pages.css';

export default function AuthCallbackPage() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const { loginWithToken } = useAuth();

    // Everything the URL says, decided during render: { token, user } or { error }.
    const result = useMemo(() => {
        const token = searchParams.get('token');
        const userB64 = searchParams.get('user');
        const authError = searchParams.get('error');

        // Handle error redirects from backend
        if (authError) {
            const errorMessages = {
                google_auth_failed: 'Google authentication failed. Please try again.',
                no_user_info: 'Could not retrieve your Google account info.',
                no_email: 'No email address found in your Google account.',
                db_error: 'Server error during login. Please try again.',
            };
            return { error: errorMessages[authError] || 'Authentication failed.' };
        }

        // Validate required params
        if (!token || !userB64) {
            return { error: 'Invalid callback — missing token or user data.' };
        }

        try {
            // Decode base64url user data
            const userJson = atob(userB64.replace(/-/g, '+').replace(/_/g, '/'));
            return { token, user: JSON.parse(userJson) };
        } catch (err) {
            console.error('Auth callback error:', err);
            return { error: 'Failed to process authentication. Please try again.' };
        }
    }, [searchParams]);
    const error = result.error || '';

    useEffect(() => {
        if (result.error) {
            const t = setTimeout(() => navigate('/login', { replace: true }), 3000);
            return () => clearTimeout(t);
        }
        // Store session via AuthContext, then leave the callback URL out of history
        loginWithToken(result.token, result.user);
        navigate('/chat', { replace: true });
    }, [result, navigate, loginWithToken]);

    return (
        <div className="cf-auth-callback">
            <Wordmark />
            {error ? (
                <div className="cf-auth-callback-msg">
                    <p className="cf-auth-error" role="alert">
                        <AlertTriangle size={14} aria-hidden="true" /> <span>{error}</span>
                    </p>
                    <p className="cf-auth-callback-sub">Taking you back to sign in.</p>
                </div>
            ) : (
                <div className="cf-auth-callback-msg" role="status">
                    <span className="cf-auth-spin" aria-hidden="true" />
                    <p>Signing you in…</p>
                </div>
            )}
        </div>
    );
}
