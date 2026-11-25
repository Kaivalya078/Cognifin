import { useEffect } from 'react';
import Navbar from '../components/landing/Navbar';
import Hero from '../components/landing/Hero';
import Features from '../components/landing/Features';
import HowItWorks from '../components/landing/HowItWorks';
import Footer from '../components/landing/Footer';
import './../styles/landing.css';

export default function LandingPage() {
    // Arriving from another page at /#features etc.: the browser's own anchor jump runs before React renders.
    useEffect(() => {
        // getElementById, not querySelector: a hash like #1abc is an invalid selector and would throw.
        const id = decodeURIComponent(window.location.hash.slice(1));
        if (id) document.getElementById(id)?.scrollIntoView();
    }, []);

    return (
        <div className="landing-page">
            <Navbar />
            <Hero />
            <Features />
            <HowItWorks />
            <Footer />
        </div>
    );
}
