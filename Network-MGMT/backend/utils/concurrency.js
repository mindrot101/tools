async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let idx = 0;
  const n = Math.max(1, Math.min(limit, items.length));
  const workers = Array.from({ length: n }, async () => {
    while (idx < items.length) {
      const i = idx++;
      try { results[i] = await fn(items[i], i); }
      catch (e) { results[i] = { error: e.message }; }
    }
  });
  await Promise.all(workers);
  return results;
}
module.exports = { mapLimit };
