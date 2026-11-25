// Run: node src/utils/deleteQueue.check.mjs   (no test framework in this frontend)
import assert from 'node:assert/strict';
import { createDeleteQueue } from './deleteQueue.js';

function fakeTimers() {
  let next = 1;
  const pending = new Map();
  return {
    setTimeout: (fn) => { const id = next++; pending.set(id, fn); return id; },
    clearTimeout: (id) => { pending.delete(id); },
    fire: () => { const fns = [...pending.values()]; pending.clear(); fns.forEach((fn) => fn()); },
  };
}

const committed = [];
const timers = fakeTimers();
const q = createDeleteQueue({ delayMs: 5000, commit: (id) => committed.push(id), timers });

q.schedule('a');
assert.deepEqual(committed, []);           // nothing until the toast expires
timers.fire();
assert.deepEqual(committed, ['a']);

q.schedule('b');
assert.equal(q.undo('b'), true);
timers.fire();
assert.deepEqual(committed, ['a']);        // undone: never committed
assert.equal(q.undo('b'), false);          // a second undo is a no-op

q.schedule('c');
q.schedule('d');
q.flush();
assert.deepEqual(committed, ['a', 'c', 'd']);
timers.fire();
assert.deepEqual(committed, ['a', 'c', 'd']); // flushed timers don't fire again

assert.equal(q.undo('a'), false);          // already committed: too late to undo
assert.equal(q.undo('zzz'), false);
q.flush();
assert.deepEqual(committed, ['a', 'c', 'd']); // never commits an id that wasn't scheduled

q.schedule('e');
q.schedule('e');                           // scheduling twice still commits once
timers.fire();
assert.deepEqual(committed, ['a', 'c', 'd', 'e']);

console.log('deleteQueue.check: ok');
