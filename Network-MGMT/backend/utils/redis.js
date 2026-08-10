const { createClient } = require('redis');
const logger = require('./logger');

const client = createClient({ url: process.env.REDIS_URL || 'redis://redis:6379' });
let connected = false;
client.on('error', (e) => logger.warn({ err: e.message }, 'redis error'));

async function connect() {
  if (connected) return;
  try { await client.connect(); connected = true; logger.info('redis connected'); }
  catch (e) { logger.warn({ err: e.message }, 'redis connect failed (caching disabled)'); }
}

async function cacheGet(key) {
  if (!connected) return null;
  try { const v = await client.get(key); return v ? JSON.parse(v) : null; } catch { return null; }
}
async function cacheSet(key, val, ttl = 30) {
  if (!connected) return;
  try { await client.set(key, JSON.stringify(val), { EX: ttl }); } catch {}
}
async function cacheDelPrefix(prefix) {
  if (!connected) return;
  try { const keys = await client.keys(`${prefix}*`); if (keys.length) await client.del(keys); } catch {}
}
// Run fn only if lock acquired; returns null if another holder has it.
async function withLock(key, ttlMs, fn) {
  if (!connected) return fn();
  let ok;
  try { ok = await client.set(key, '1', { NX: true, PX: ttlMs }); } catch { return fn(); }
  if (!ok) return null;
  try { return await fn(); } finally { try { await client.del(key); } catch {} }
}


async function publish(channel, payload) {
  if (!connected) return;
  try { await client.publish(channel, JSON.stringify(payload)); } catch {}
}
async function subscribe(channel, handler) {
  try {
    const sub = client.duplicate();
    sub.on('error', (e) => logger.warn({ err: e.message }, 'redis sub error'));
    await sub.connect();
    await sub.subscribe(channel, (msg) => { try { handler(JSON.parse(msg)); } catch {} });
    return sub;
  } catch (e) { logger.warn({ err: e.message }, 'redis subscribe failed'); }
}

module.exports = { client, connect, cacheGet, cacheSet, cacheDelPrefix, withLock, publish, subscribe };
