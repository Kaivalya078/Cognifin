// Run: node src/utils/citations.check.mjs   (no test framework in this frontend)
import assert from 'node:assert/strict';
import { linkCitations } from './citations.js';

const ev = [
  { chunk_id: 'chunk_12', page_number: 17 },
  { chunk_id: 'fin_3', page_number: 0 },
  { chunk_id: 'chunk_1', page_number: 4 },
  { chunk_id: 'chunk_2', page_number: 0 },
];

assert.equal(linkCitations('Rev ₹2,40,893 crore [chunk_12].', ev), 'Rev ₹2,40,893 crore [p.17](#cite-chunk_12).');
assert.equal(linkCitations('Q2 [fin_3]', ev), 'Q2 [table](#cite-fin_3)');
assert.equal(linkCitations('a [chunk_1, chunk_2] b', ev), 'a [p.4](#cite-chunk_1) [source](#cite-chunk_2) b');
assert.equal(linkCitations('a [chunk_1][chunk_2] b', ev), 'a [p.4](#cite-chunk_1) [source](#cite-chunk_2) b');
assert.equal(linkCitations('a (chunk_1) b', ev), 'a [p.4](#cite-chunk_1) b');
assert.equal(linkCitations('a chunk_1 b', ev), 'a [p.4](#cite-chunk_1) b');
assert.equal(linkCitations('a [chunk_99].', ev), 'a.');
assert.equal(linkCitations('a [chunk_99][chunk_1].', ev), 'a [p.4](#cite-chunk_1).');
assert.equal(linkCitations('x [chunk_12]', [{ chunk_id: '[expanded]chunk_12', page_number: 17 }]), 'x [p.17](#cite-chunk_12)');
assert.equal(linkCitations('x [chunk_12]', [{ chunk_id: '[TCS]:chunk_12', page_number: 17 }]), 'x [p.17](#cite-chunk_12)');
assert.equal(linkCitations('no markers here', ev), 'no markers here');
assert.equal(linkCitations('x [chunk_12]', null), 'x [source](#cite-chunk_12)');
assert.equal(linkCitations('x [chunk_12]', []), 'x [source](#cite-chunk_12)');
assert.equal(linkCitations('| Rev | 2,40,893 [chunk_12] |', ev), '| Rev | 2,40,893 [p.17](#cite-chunk_12) |');
assert.equal(linkCitations('', ev), '');
assert.equal(linkCitations(undefined, ev), '');

console.log('citations.check: ok');
