// Deferred deletes behind an Undo toast: the server call waits until the toast expires.
// flush() sends everything still pending (on pagehide); a delete lost with a killed tab
// just leaves the chat in place, which is the safe way to fail.
export function createDeleteQueue({ delayMs, commit, timers = globalThis }) {
  const pending = new Map(); // id -> timer

  const run = (id) => {
    pending.delete(id);
    commit(id);
  };

  return {
    schedule(id) {
      if (pending.has(id)) timers.clearTimeout(pending.get(id));
      pending.set(id, timers.setTimeout(() => run(id), delayMs));
    },
    undo(id) {
      if (!pending.has(id)) return false;
      timers.clearTimeout(pending.get(id));
      pending.delete(id);
      return true;
    },
    flush() {
      for (const [id, t] of [...pending]) {
        timers.clearTimeout(t);
        run(id);
      }
    },
  };
}
