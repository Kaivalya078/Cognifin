import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import Navbar from '../components/landing/Navbar';
import Hero from '../components/landing/Hero';
import ProductWindow from '../components/landing/ProductWindow';
import HowItWorks from '../components/landing/HowItWorks';
import Proof from '../components/landing/Proof';
import Coverage from '../components/landing/Coverage';
import AskCta from '../components/landing/AskCta';
import Footer from '../components/landing/Footer';
import '../styles/landing-v2.css';

gsap.registerPlugin(ScrollTrigger);

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export default function LandingPage() {
    const [metrics, setMetrics] = useState(null);
    const root = useRef(null);

    useEffect(() => {
        fetch('/metrics.json')
            .then((r) => (r.ok ? r.json() : null))
            .then((m) => setMetrics(m && typeof m === 'object' ? m : null))
            .catch(() => setMetrics(null));
    }, []);

    // Smooth scroll on this page only (the chat has nested scroll areas). Off under reduced motion.
    useEffect(() => {
        const jump = () => {
            const id = decodeURIComponent(window.location.hash.slice(1));
            return id ? document.getElementById(id) : null;
        };
        if (reducedMotion()) {
            jump()?.scrollIntoView();
            return undefined;
        }
        const lenis = new Lenis({ anchors: true })  // sections' own top padding clears the sticky navbar;
        const tick = (t) => lenis.raf(t * 1000);
        lenis.on('scroll', ScrollTrigger.update);
        gsap.ticker.add(tick);
        gsap.ticker.lagSmoothing(0);
        const target = jump();
        if (target) lenis.scrollTo(target, { immediate: true });
        return () => {
            gsap.ticker.remove(tick);
            lenis.destroy();
        };
    }, []);

    // One scroll moment: the product window rises into place, once. Never hidden by CSS.
    useLayoutEffect(() => {
        if (reducedMotion()) return undefined;
        const ctx = gsap.context(() => {
            gsap.from('.cf-window', {
                y: 48,
                opacity: 0,
                duration: 0.9,
                ease: 'power3.out',
                scrollTrigger: { trigger: '.cf-window', start: 'top 85%', once: true },
            });
        }, root);
        return () => ctx.revert();
    }, []);

    return (
        <div className="cf-landing" ref={root}>
            <Navbar />
            <main>
                <Hero />
                <ProductWindow />
                <HowItWorks metrics={metrics} />
                <Proof metrics={metrics} />
                <Coverage />
                <AskCta />
            </main>
            <Footer />
        </div>
    );
}
