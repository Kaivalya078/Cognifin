import { useLayoutEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import gsap from 'gsap';
import { HERO_CASE as C } from '../../data/examples';

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// The one orchestrated moment on the page: a filing page is read, the figure lights up,
// and the cited answer lifts out. Decorative (aria-hidden); the text carries the message.
function FilingScan() {
    const root = useRef(null);

    useLayoutEffect(() => {
        if (reducedMotion()) return undefined;
        const ctx = gsap.context(() => {
            const page = root.current.querySelector('.cf-scan-page');
            const row = root.current.querySelector('.cf-scan-row-hit');
            const rowY = row.offsetTop + row.offsetHeight / 2;
            const tl = gsap.timeline({ repeat: -1, repeatDelay: 1.2, defaults: { ease: 'power2.out' } });
            tl.set('.cf-scan-line', { y: 0, opacity: 0 })
                .set(row, { '--hit': 0 })
                .set('.cf-scan-answer', { opacity: 0, y: 18 })
                .to('.cf-scan-line', { opacity: 1, duration: 0.25 })
                .to('.cf-scan-line', { y: rowY, duration: 1.3, ease: 'none' })
                .to(row, { '--hit': 1, duration: 0.3 })
                .to('.cf-scan-line', { y: page.offsetHeight - 2, duration: 1, ease: 'none' }, '<')
                .to('.cf-scan-line', { opacity: 0, duration: 0.25 })
                .to('.cf-scan-answer', { opacity: 1, y: 0, duration: 0.6 }, '-=0.1')
                .to({}, { duration: 3 })
                .to('.cf-scan-answer', { opacity: 0, y: 8, duration: 0.4, ease: 'power1.in' })
                .to(row, { '--hit': 0, duration: 0.4 }, '<');
        }, root);
        return () => ctx.revert();
    }, []);

    return (
        <div className="cf-scan" ref={root} aria-hidden="true">
            <div className="cf-scan-page">
                <div className="cf-scan-head">
                    <span><b>{C.company}</b> {C.document}</span>
                    <span>p. {C.page}</span>
                </div>
                <div className="cf-bar" style={{ width: '58%', height: 9, marginTop: 20 }} />
                <div className="cf-bar" style={{ width: '94%' }} />
                <div className="cf-bar" style={{ width: '88%' }} />
                <div className="cf-bar" style={{ width: '72%' }} />
                <div className="cf-scan-table">
                    <div className="cf-scan-row cf-scan-row-head"><span>Particulars</span><span>FY24 · ₹ crore</span></div>
                    <div className="cf-scan-row cf-scan-row-hit"><span>{C.rowLabel}</span><span>{C.rowValue}</span></div>
                    <div className="cf-scan-row"><span className="cf-bar" style={{ width: '38%', margin: 0 }} /><span className="cf-bar" style={{ width: 54, margin: 0 }} /></div>
                    <div className="cf-scan-row"><span className="cf-bar" style={{ width: '46%', margin: 0 }} /><span className="cf-bar" style={{ width: 62, margin: 0 }} /></div>
                </div>
                <div className="cf-bar" style={{ width: '90%', marginTop: 22 }} />
                <div className="cf-bar" style={{ width: '83%' }} />
                <div className="cf-bar" style={{ width: '64%' }} />
                <div className="cf-scan-line" />
            </div>
            <div className="cf-scan-answer">
                <p className="cf-scan-q">{C.question}</p>
                <p className="cf-scan-a">
                    {C.answer} <b>{C.figure}</b>{C.tail} <span className="cf-chip">p.{C.page}</span>
                </p>
            </div>
        </div>
    );
}

export default function Hero() {
    return (
        <section className="cf-hero">
            <div className="cf-hero-copy">
                <h1 className="cf-h1">Every answer points to its page.</h1>
                <p className="cf-lead">
                    Ask about any NIFTY&nbsp;50 company. Cognifin reads the annual reports and quarterly
                    results, answers in plain language, and shows you the exact line it used.
                </p>
                <div className="cf-hero-actions">
                    <Link to="/chat" className="cf-btn cf-btn-solid">Try a question</Link>
                    <Link to="/engineering" className="cf-btn cf-btn-ghost">See how it's measured</Link>
                </div>
            </div>
            <FilingScan />
        </section>
    );
}
