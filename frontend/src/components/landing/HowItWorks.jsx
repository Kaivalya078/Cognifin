export default function HowItWorks({ metrics }) {
    const docs = metrics?.index?.documents;
    const corpus = Number.isFinite(docs)
        ? `${docs} filings, annual reports and quarterly results,`
        : 'the annual reports and quarterly results';
    const steps = [
        ['Ask', 'Type a question about any covered company, in plain language.'],
        ['Search', `Cognifin searches ${corpus} by meaning and by keyword, then reranks the best passages.`],
        ['Answer', 'Figures are checked against a table of verified results, and every claim carries a chip that opens its page.'],
    ];
    return (
        <section id="how" className="cf-section cf-block">
            <h2 className="cf-h2">How it works</h2>
            <ol className="cf-steps">
                {steps.map(([title, body], i) => (
                    <li key={title} className="cf-step">
                        <span className="cf-step-n" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>
                        <h3 className="cf-step-title">{title}</h3>
                        <p className="cf-step-body">{body}</p>
                    </li>
                ))}
            </ol>
        </section>
    );
}
