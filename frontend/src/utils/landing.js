// Pure helpers for the landing page and the /chat?q= handoff.
import { pct } from './metricsFormat.js';

const MAX_Q = 500;
const isNum = (x) => typeof x === 'number' && Number.isFinite(x);

export function chatHref(question) {
  const q = (question || '').trim();
  return q ? `/chat?q=${encodeURIComponent(q)}` : '/chat';
}

export function readQuestionParam(search) {
  const q = (new URLSearchParams(search || '').get('q') || '').trim();
  return q ? q.slice(0, MAX_Q) : null;
}

// The four proof figures, or null unless every input is a real number (never placeholders).
export function proofItems(m) {
  const faith = m?.answers?.faithfulness;
  const correct = m?.answers?.correctness;
  const companies = m?.golden_set?.companies;
  const filings = m?.index?.documents;
  if (![faith, correct, companies, filings].every(isNum)) return null;
  return [
    { value: pct(faith), label: 'of claims backed by the passages shown' },
    { value: pct(correct), label: 'correctness vs the answer key; partial counts ½' },
    { value: String(companies), label: 'NIFTY 50 companies covered' },
    { value: String(filings), label: 'annual reports and results indexed' },
  ];
}
