// One request at a time, with cancellation and a delay after completion.
// refresh() also supports a one-off refresh while automatic polling is stopped.
export function createPoller(task, interval, { timeout = 10000 } = {}) {
  let active = false, pending = null, controller = null, timer = null;
  let restartAfterAbort = false;

  function refresh() {
    if (pending) return pending;
    clearTimeout(timer);
    const current = new AbortController();
    controller = current;
    const deadline = setTimeout(() => current.abort(), timeout);
    pending = Promise.resolve().then(async () => {
      try {
        if (!current.signal.aborted) await task(current.signal);
      } catch (error) {
        if (!current.signal.aborted) console.error('Dashboard refresh failed', error);
      } finally {
        clearTimeout(deadline);
        pending = null;
        controller = null;
        if (active) timer = setTimeout(refresh, restartAfterAbort ? 0 : interval);
        restartAfterAbort = false;
      }
    });
    return pending;
  }

  return {
    refresh,
    start() {
      if (active) return;
      active = true;
      if (pending && controller?.signal.aborted) restartAfterAbort = true;
      else refresh();
    },
    stop() {
      active = false;
      restartAfterAbort = false;
      clearTimeout(timer);
      controller?.abort();
    },
  };
}
