import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CTA_EXAMPLES } from '../../data/examples';
import { chatHref } from '../../utils/landing';

export default function AskCta() {
    const [q, setQ] = useState('');
    const navigate = useNavigate();
    const ask = (question) => question.trim() && navigate(chatHref(question));

    return (
        <section className="cf-section cf-block cf-cta" aria-labelledby="cf-cta-h">
            <h2 id="cf-cta-h" className="cf-h2">Ask your first question.</h2>
            <form className="cf-ask" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
                <label htmlFor="cf-ask-input" className="cf-visually-hidden">Your question</label>
                <input
                    id="cf-ask-input"
                    className="cf-ask-input"
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="What was TCS's revenue in FY24?"
                    autoComplete="off"
                    maxLength={500}
                />
                <button type="submit" className="cf-btn cf-btn-solid">Ask</button>
            </form>
            <div className="cf-ask-examples">
                {CTA_EXAMPLES.map((ex) => (
                    <button key={ex.label} type="button" className="cf-ask-chip" onClick={() => ask(ex.question)}>
                        {ex.label}
                    </button>
                ))}
            </div>
        </section>
    );
}
