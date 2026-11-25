// Run: node src/utils/landing.check.mjs   (from frontend/)
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { chatHref, proofItems, readQuestionParam } from './landing.js';
import { COMPANIES } from '../data/companies.js';

const metrics = JSON.parse(readFileSync(new URL('../../public/metrics.json', import.meta.url), 'utf8'));

// chatHref
assert.equal(chatHref('  What was X?  '), '/chat?q=What%20was%20X%3F');
assert.equal(chatHref('   '), '/chat');
assert.equal(chatHref(undefined), '/chat');

// proofItems: real metrics → 4 non-empty items; anything incomplete → null
const items = proofItems(metrics);
assert.equal(items.length, 4);
for (const it of items) assert.ok(it.value && it.label && !/undefined|NaN|—/.test(it.value));
assert.equal(items[2].value, String(metrics.golden_set.companies));
assert.equal(items[3].value, String(metrics.index.documents));
assert.equal(proofItems({}), null);
assert.equal(proofItems(null), null);
assert.equal(proofItems({ ...metrics, answers: { ...metrics.answers, faithfulness: null } }), null);

// readQuestionParam
assert.equal(readQuestionParam('?q=Hi%20there'), 'Hi there');
assert.equal(readQuestionParam('?q=%20%20'), null);
assert.equal(readQuestionParam(''), null);
assert.equal(readQuestionParam('?q=' + 'a'.repeat(600)).length, 500);

// companies: matches the eval's company count, unique, no KWIL (no reports)
assert.equal(COMPANIES.length, metrics.golden_set.companies);
assert.equal(new Set(COMPANIES).size, COMPANIES.length);
assert.ok(!COMPANIES.includes('KWIL'));

console.log('landing.check: ok');
