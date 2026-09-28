// Place measurements by wall-clock time so pauses remain gaps, not old bars at "now".
export function buildTimeline(samples, key, now = Date.now(), slots = 360, interval = 5000) {
  const values = new Array(slots).fill(null);
  const current = Math.floor(now / interval);
  for (const sample of samples) {
    const index = slots - 1 - (current - Math.floor(sample.timestamp / interval));
    if (index >= 0 && index < slots) values[index] = sample[key];
  }
  return values;
}
