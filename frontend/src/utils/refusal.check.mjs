// Run: node src/utils/refusal.check.mjs   (no test framework in this frontend)
import assert from 'node:assert/strict';
import { isRefusal } from './refusal.js';

assert.equal(isRefusal('Not available in the provided documents.'), true);
assert.equal(isRefusal('  Not available in the provided documents \n'), true);
assert.equal(isRefusal('## Overview\n| X | Data Not Available |'), false);
assert.equal(isRefusal('Revenue rose. Not available in the provided documents.'), false);
assert.equal(isRefusal('⚠️ Server error (500)'), false);
assert.equal(isRefusal(''), false);
assert.equal(isRefusal(undefined), false);

console.log('refusal.check: ok');
