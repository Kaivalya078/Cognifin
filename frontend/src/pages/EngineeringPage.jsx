import { useEffect, useState } from 'react';
import Navbar from '../components/landing/Navbar';
import Footer from '../components/landing/Footer';
import { pct, secs, usd, kindRows } from '../utils/metricsFormat';
import '../styles/landing-v2.css';
import '../styles/pages.css';

const README_URL =
  'https://github.com/Kaivalya078/Cognifin/blob/main/backend/tests/eval_reports/README.md';

// Static copy from the v2 baseline write-up (backend/tests/eval_reports/README.md).
// Update by hand when a new run changes it.
const WEAK_SPOTS = [
  'About 1 in 5 cited answers is cited only by a code fill, which attaches a source when every figure in a sentence matches a passage exactly. Sentences without figures rely on the model citing them itself.',
  '3 of 8 quarterly-figure questions were refused although the figures are in the financials table.',
  'About 6 of 100 answers are genuinely wrong: a nearby figure from a different line, or a refusal where the answer exists.',
  'The judge model is about ±1 point noisy on correctness, in both directions.',
];

const runDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';

function Results({ m }) {
  const a = m.answers ?? {};
  const r = m.retrieval ?? {};
  const lat = m.latency_ms ?? {};
  const cost = m.cost_usd ?? {};
  const idx = m.index ?? {};
  const tiles = [
    ['Faithfulness', pct(a.faithfulness), 'claims backed by the passages shown'],
    ['Correctness', pct(a.correctness), 'vs the answer key; partial counts ½'],
    ['Retrieval hit@8', pct(r['hit@8']), 'right page in the top 8'],
    ['Latency p50', secs(lat.p50), `p95 ${secs(lat.p95)}`],
  ];
  const facts = [
    ['Refusal accuracy', pct(a.refusal_accuracy)],
    ['Citation validity', pct(a.citation_validity)],
    ['Answers with a citation', pct(a.cited_share)],
    ['Retrieval hit@3', pct(r['hit@3'])],
    ['Cost per question', `${usd(cost.per_question)} + ${usd(cost.judge_per_question)} judge`],
    ['Index', idx.documents
      ? `${idx.documents} documents, ${idx.chunks?.toLocaleString('en-IN')} chunks, ${(idx.disk_mb / 1024).toFixed(1)} GB`
      : 'Not recorded'],
  ];

  return (
    <>
      <p className="cf-eng-meta">
        <span>Eval run {runDate(m.generated_at)}</span>
        <span>{m.golden_set?.cases} questions</span>
        <span>{m.golden_set?.companies} companies</span>
        {idx.documents ? <span>{idx.documents} filings indexed</span> : null}
      </p>

      <div className="cf-eng-tiles">
        {tiles.map(([label, value, sub]) => (
          <div className="cf-eng-tile" key={label}>
            <span className="cf-eng-tile-label">{label}</span>
            <span className="cf-eng-tile-value">{value}</span>
            <span className="cf-eng-tile-sub">{sub}</span>
          </div>
        ))}
      </div>

      <div className="cf-eng-columns">
        <section>
          <h2>How it's measured</h2>
          <p>
            {m.golden_set?.cases} questions over {m.golden_set?.companies} companies' annual reports and quarterly
            filings. Every answer key was checked against the page it comes from, twice, by an LLM; 10 were
            also spot-checked by hand.
          </p>
          <p>
            Each question runs through the same pipeline the chat uses: retrieval, reranking, the numeric
            router and generation. Nothing is special-cased for the eval.
          </p>
          <p>
            A judge model splits each answer into single claims and checks every claim against the exact
            passages the app was shown. Faithfulness is the share of claims those passages support (the
            method RAGAS calls faithfulness).
          </p>
          <div className="cf-eng-weak">
            <h3>Known weak spots</h3>
            <ul>{WEAK_SPOTS.map((w) => <li key={w}>{w}</li>)}</ul>
          </div>
        </section>

        <section>
          <h2>By question type</h2>
          <table className="cf-eng-table">
            <thead><tr><th>Type</th><th>n</th><th>Correct</th><th>Faithful</th></tr></thead>
            <tbody>
              {kindRows(a.by_kind).map((k) => (
                <tr key={k.key}><td>{k.label}</td><td>{k.n}</td><td>{pct(k.correctness)}</td><td>{pct(k.faithfulness)}</td></tr>
              ))}
            </tbody>
          </table>
          <dl className="cf-eng-facts">
            {facts.map(([k, v]) => (<div key={k}><dt>{k}</dt><dd>{v}</dd></div>))}
          </dl>
        </section>
      </div>

      <section className="cf-eng-repro">
        <h2>Reproduce</h2>
        <code>PYTHONUTF8=1 python -m tests.eval_answers --label NAME</code>
        <p>Models: {m.model} (answers), {m.judge_model} (judge).</p>
        <p className="cf-eng-links">
          <a className="cf-link" href="/metrics.json">Raw metrics.json</a>
          <a className="cf-link" href={README_URL} target="_blank" rel="noreferrer">Eval write-up</a>
        </p>
      </section>
    </>
  );
}

export default function EngineeringPage() {
  const [state, setState] = useState({ status: 'loading', data: null });

  useEffect(() => {
    fetch('/metrics.json')
      .then((res) => {
        if (!res.ok) throw new Error(res.status);
        return res.json();
      })
      .then((data) => setState({ status: 'ok', data }))
      .catch(() => setState({ status: 'error', data: null }));
  }, []);

  return (
    <div className="cf-landing">
      <Navbar />
      <main className="cf-section cf-eng">
        <span className="cf-eng-eyebrow">Evaluation</span>
        <h1 className="cf-h1 cf-eng-title">How Cognifin is measured</h1>
        {state.status === 'loading' && <p className="cf-eng-meta">Loading eval results…</p>}
        {state.status === 'error' && <p className="cf-eng-meta">Eval results are not available right now.</p>}
        {state.status === 'ok' && <Results m={state.data} />}
      </main>
      <Footer />
    </div>
  );
}
