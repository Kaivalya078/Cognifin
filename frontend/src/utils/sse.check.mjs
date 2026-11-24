// Run: node src/utils/sse.check.mjs   (no test framework in this frontend)
import assert from 'node:assert/strict';
import { takeFrames } from './sse.js';

// Complete frames are parsed, a partial tail is kept for the next read.
let r = takeFrames('event: stage\ndata: {"name":"retrieval"}\n\nevent: token\ndata: {"te');
assert.deepEqual(r.frames, [{ type: 'stage', data: { name: 'retrieval' } }]);
assert.equal(r.rest, 'event: token\ndata: {"te');

// CRLF framing (from a proxy) splits the same way.
r = takeFrames('event: token\r\ndata: {"text":"a"}\r\n\r\n');
assert.deepEqual(r.frames, [{ type: 'token', data: { text: 'a' } }]);
assert.equal(r.rest, '');

// Comment / keep-alive and data-less frames are skipped, not thrown on.
r = takeFrames(': ping\n\nevent: stage\n\nevent: final\ndata: {"ok":true}\n\n');
assert.deepEqual(r.frames, [{ type: 'final', data: { ok: true } }]);

console.log('sse.check: ok');
