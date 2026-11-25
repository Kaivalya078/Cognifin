import Navbar from '../components/landing/Navbar';
import Hero from '../components/landing/Hero';
import Footer from '../components/landing/Footer';
import '../styles/landing-v2.css';

export default function LandingPage() {
    return (
        <div className="cf-landing">
            <Navbar />
            <main>
                <Hero />
            </main>
            <Footer />
        </div>
    );
}
