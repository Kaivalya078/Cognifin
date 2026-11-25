// Run: node src/utils/metricsFormat.check.mjs   (no test framework in this frontend)
import assert from 'node:assert/strict';
import { pct, secs, usd, kindRows } from './metricsFormat.js';

assert.equal(pct(0.994413407821229), '99.4%');
assert.equal(pct(1), '100%');
assert.equal(pct(0.87), '87%');
assert.equal(pct(0.021052631578947368), '2.1%');
assert.equal(pct(null), '—');
assert.equal(pct(undefined), '—');
assert.equal(pct(NaN), '—');
assert.equal(secs(9266), '9.3 s');
assert.equal(secs(15035.3), '15.0 s');
assert.equal(secs(null), '—');
assert.equal(usd(0.000672), '$0.00067');
assert.equal(usd(0.000708), '$0.00071');
assert.equal(usd(null), '—');

const rows = kindRows({
  table: { n: 46, correctness: 0.837, faithfulness: 1 },
  refusal: { n: 5, correctness: 1, faithfulness: null },
  narrative: { n: 41, correctness: 0.939, faithfulness: 0.991 },
});
assert.deepEqual(rows.map((r) => r.key), ['narrative', 'table', 'refusal']);
assert.equal(rows[1].label, 'Table figures');
assert.equal(rows[2].faithfulness, null);
assert.deepEqual(kindRows(null), []);

console.log('metricsFormat.check: ok');
