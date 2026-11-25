/**
 * Register Page: Google OAuth, or name, email, password and confirm password.
 */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import AuthShell, { Field, PasswordField, AuthError } from '../components/auth/AuthShell';

export default function RegisterPage() {
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const { register } = useAuth();
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        // Client-side validation
        if (password.length < 6) {
            setError('Password must be at least 6 characters.');
            return;
        }
        if (password !== confirmPassword) {
            setError('Passwords do not match.');
            return;
        }

        setIsLoading(true);
        try {
            await register(name, email, password);
            navigate('/login');
        } catch (err) {
            setError(err.message || 'Registration failed.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <AuthShell title="Create your account" subtitle="Use Google or your email.">
            <form onSubmit={handleSubmit} className="cf-auth-fields">
                <Field id="name" label="Name" type="text" value={name}
                    onChange={(e) => setName(e.target.value)} placeholder="Your name"
                    required autoComplete="name" />
                <Field id="email" label="Email" type="email" value={email}
                    onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com"
                    required autoComplete="email" />
                <PasswordField id="password" label="Password" value={password}
                    onChange={(e) => setPassword(e.target.value)} placeholder="At least 6 characters"
                    required autoComplete="new-password" />
                <PasswordField id="confirmPassword" label="Confirm password" value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required autoComplete="new-password" />
                <AuthError>{error}</AuthError>
                <button type="submit" className="cf-btn cf-btn-solid cf-auth-submit"
                    disabled={isLoading || !name || !email || !password || !confirmPassword}>
                    {isLoading ? 'Creating account…' : 'Create account'}
                </button>
            </form>
            <p className="cf-auth-swap">
                Already have an account? <Link to="/login" className="cf-link">Sign in</Link>
            </p>
        </AuthShell>
    );
}
