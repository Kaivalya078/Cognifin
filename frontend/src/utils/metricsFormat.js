// Formatting for /engineering (values come from public/metrics.json).

const DASH = '—';
const ok = (x) => typeof x === 'number' && Number.isFinite(x);

export const pct = (x, digits = 1) =>
  ok(x) ? `${(x * 100).toFixed(digits).replace(/\.0+$/, '')}%` : DASH;

export const secs = (ms) => (ok(ms) ? `${(ms / 1000).toFixed(1)} s` : DASH);

export const usd = (x) => (ok(x) ? `$${x.toPrecision(2)}` : DASH);

const KINDS = [
  ['narrative', 'Narrative'],
  ['table', 'Table figures'],
  ['numeric', 'Quarterly numbers'],
  ['refusal', 'Should refuse'],
];

export const kindRows = (byKind) =>
  KINDS.filter(([key]) => byKind?.[key]).map(([key, label]) => ({
    key,
    label,
    n: byKind[key].n,
    correctness: byKind[key].correctness,
    faithfulness: byKind[key].faithfulness,
  }));
