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
        if (window.location.hash) document.querySelector(window.location.hash)?.scrollIntoView();
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
