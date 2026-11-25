// Run: node src/utils/chatFormat.check.mjs   (no test framework in this frontend)
import assert from 'node:assert/strict';
import { sourceGroups, detailsItems, stageLine, docLabel } from './chatFormat.js';

const ev = [
  { chunk_id: 'chunk_2', document_label: 'TCS AR 2023-24', page_number: 112 },
  { chunk_id: 'chunk_1', document_label: 'TCS AR 2023-24', page_number: 56 },
  { chunk_id: 'chunk_3', document_label: 'TCS AR 2023-24', page_number: 56 },
  { chunk_id: 'chunk_4', document_label: 'INFY AR 2024-25', page_number: 0 },
  { chunk_id: 'chunk_5', document_label: 'Uncited', page_number: 9 },
  { chunk_id: 'chunk_6', page_number: 3 },
];
const g = sourceGroups(ev, ['chunk_2', 'chunk_1', 'chunk_3', 'chunk_4', 'chunk_6']);
assert.deepEqual(g.map((x) => x.label), ['TCS AR 2023-24', 'INFY AR 2024-25', 'chunk_6']);
assert.deepEqual(g[0].items.map((i) => i.page_number), [56, 112]);
assert.deepEqual(sourceGroups(ev, []), []);
assert.deepEqual(sourceGroups(undefined, undefined), []);

assert.deepEqual(detailsItems({ confidence: 0.751, latency_ms: 10671, cached: true, intent: 'comparison' }),
  ['Confidence 75%', '10.7 s', 'Cached', 'Comparison']);
assert.deepEqual(detailsItems({ confidence: 0.5, intent: 'temporal' }), ['Confidence 50%', 'Trend']);
assert.deepEqual(detailsItems({ confidence: 0.5, intent: 'single_entity' }), ['Confidence 50%']);
assert.deepEqual(detailsItems({ confidence: 0.5, intent: 'lookup' }), ['Confidence 50%']);
assert.deepEqual(detailsItems({}), []);

assert.equal(stageLine([]), 'Searching filings…');
assert.equal(stageLine([{ name: 'retrieval', ms: 120 }]), 'Searching filings…');
assert.equal(stageLine([{ name: 'retrieval' }, { name: 'reranking' }]), 'Ranking passages…');
assert.equal(stageLine([{ name: 'retrieval' }, { name: 'context_assembly' }]), 'Writing answer…');
assert.ok(!/FAISS|BM25|ms/.test(stageLine([{ name: 'retrieval', ms: 5 }])));

assert.equal(docLabel('TCS_Annual_Report_2024_v1'), 'TCS Annual Report 2024');
assert.equal(docLabel('TCS AR 2023-24'), 'TCS AR 2023-24');
assert.equal(docLabel(''), '');
assert.deepEqual(sourceGroups([{ chunk_id: 'c', document_label: 'HUL_AR_2025_v2', page_number: 4 }], ['c']).map((x) => x.label), ['HUL AR 2025']);

console.log('chatFormat.check: ok');
