/**
 * Login Page: Google OAuth or email and password.
 */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import AuthShell, { Field, PasswordField, AuthError } from '../components/auth/AuthShell';

export default function LoginPage() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const { login } = useAuth();
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            await login(email, password);
            navigate('/chat');
        } catch (err) {
            setError(err.message || 'Invalid email or password.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <AuthShell title="Sign in" subtitle="Use Google or your email.">
            <form onSubmit={handleSubmit} className="cf-auth-fields">
                <Field id="email" label="Email" type="email" value={email}
                    onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com"
                    required autoComplete="email" />
                <PasswordField id="password" label="Password" value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required autoComplete="current-password" />
                <AuthError>{error}</AuthError>
                <button type="submit" className="cf-btn cf-btn-solid cf-auth-submit"
                    disabled={isLoading || !email || !password}>
                    {isLoading ? 'Signing in…' : 'Sign in'}
                </button>
            </form>
            <p className="cf-auth-swap">
                No account? <Link to="/register" className="cf-link">Create one</Link>
            </p>
        </AuthShell>
    );
}
