import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
import '../../styles/landing-v2.css';

const LINKS = [
    { label: 'Product', href: '/#product' },
    { label: 'How it works', href: '/#how' },
    { label: 'Engineering', to: '/engineering' },
];

export function Wordmark() {
    return <span className="cf-wordmark">cognifin<span className="cf-wordmark-dot">.</span></span>;
}

export default function Navbar() {
    const [open, setOpen] = useState(false);
    const menuBtn = useRef(null);

    useEffect(() => {
        if (!open) return undefined;
        const onKey = (e) => {
            if (e.key !== 'Escape') return;
            setOpen(false);
            menuBtn.current?.focus();  // don't drop focus to <body>
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [open]);

    const close = () => setOpen(false);
    const item = (l, cls) => (l.to
        ? <Link key={l.label} to={l.to} className={cls} onClick={close}>{l.label}</Link>
        : <a key={l.label} href={l.href} className={cls} onClick={close}>{l.label}</a>);

    return (
        <header className="cf-nav">
            <nav className="cf-nav-inner" aria-label="Main">
                <Link to="/" className="cf-nav-home" aria-label="Cognifin home" onClick={close}><Wordmark /></Link>
                <div className="cf-nav-links">{LINKS.map((l) => item(l, 'cf-nav-link'))}</div>
                <Link to="/chat" className="cf-btn cf-btn-ghost cf-nav-cta">Open app</Link>
                <button
                    ref={menuBtn}
                    type="button"
                    className="cf-nav-menu"
                    aria-label="Menu"
                    aria-expanded={open}
                    aria-controls="cf-nav-sheet"
                    onClick={() => setOpen((o) => !o)}
                >
                    {open ? <X size={20} /> : <Menu size={20} />}
                </button>
            </nav>
            {open && (
                <nav id="cf-nav-sheet" className="cf-nav-sheet" aria-label="Main (menu)">
                    {LINKS.map((l) => item(l, 'cf-nav-sheet-link'))}
                    <Link to="/chat" className="cf-btn cf-btn-solid" onClick={close}>Open app</Link>
                </nav>
            )}
        </header>
    );
}
