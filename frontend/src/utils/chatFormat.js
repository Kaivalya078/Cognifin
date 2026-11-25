// Formatting for chat answers: the Sources row, the Details summary, the live stage line.
import { pct, secs } from './metricsFormat.js';

// Plain words for the server's stage names (no stack names in the chat UI).
export const STAGE_LABELS = {
  retrieval: 'Searching filings',
  reranking: 'Ranking passages',
  intelligent_retrieve: 'Searching filings',
  context_assembly: 'Reading passages',
};

// File-style labels read as names: "TCS_Annual_Report_2024_v1" -> "TCS Annual Report 2024".
export const docLabel = (label) => (label || '').replace(/_/g, ' ').replace(/\s+v\d+$/i, '').trim();

// Only question types worth naming to a reader; the rest stay silent.
const INTENTS = { comparison: 'Comparison', compare: 'Comparison', temporal: 'Trend', trend: 'Trend' };

// Cited evidence grouped by document, first-cited first; each group's pages ascending, one per page.
export function sourceGroups(evidence, citations) {
  const cited = new Set(citations || []);
  const groups = new Map();
  for (const item of evidence || []) {
    if (!cited.has(item.chunk_id)) continue;
    const label = docLabel(item.document_label) || item.chunk_id;
    if (!groups.has(label)) groups.set(label, []);
    const items = groups.get(label);
    if (!items.some((i) => i.page_number === item.page_number)) items.push(item);
  }
  return [...groups].map(([label, items]) => ({
    label,
    items: items.sort((a, b) => (a.page_number || 0) - (b.page_number || 0)),
  }));
}

export function detailsItems(p) {
  const out = [];
  if (typeof p?.confidence === 'number') out.push(`Confidence ${pct(p.confidence, 0)}`);
  if (p?.latency_ms) out.push(secs(p.latency_ms));
  if (p?.cached) out.push('Cached');
  if (INTENTS[p?.intent]) out.push(INTENTS[p.intent]);
  return out;
}

export function stageLine(stages) {
  if (!stages?.length) return 'Searching filings…';
  const last = stages[stages.length - 1].name;
  if (last === 'context_assembly') return 'Writing answer…';
  return `${STAGE_LABELS[last] || 'Searching filings'}…`;
}
