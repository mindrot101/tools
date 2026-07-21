// Minimal API client. Auth held in sessionStorage (this is a first-party app
// served by our own container, not a sandboxed artifact).
const Auth = {
  get mode() { return sessionStorage.getItem('vxv_mode'); },
  get cred() { return sessionStorage.getItem('vxv_cred'); },
  set(mode, cred) { sessionStorage.setItem('vxv_mode', mode); sessionStorage.setItem('vxv_cred', cred); },
  clear() { sessionStorage.removeItem('vxv_mode'); sessionStorage.removeItem('vxv_cred'); },
  headers() {
    const h = { 'Content-Type': 'application/json' };
    if (this.mode === 'key') h['X-API-Key'] = this.cred;
    else if (this.mode === 'token') h['Authorization'] = 'Bearer ' + this.cred;
    return h;
  }
};

const API = {
  async get(path) {
    const r = await fetch('/api' + path, { headers: Auth.headers() });
    if (r.status === 401) { Auth.clear(); location.reload(); }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch('/api' + path, { method: 'POST', headers: Auth.headers(), body: JSON.stringify(body || {}) });
    if (r.status === 401) { Auth.clear(); location.reload(); }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  },
  async del(path) {
    const r = await fetch('/api' + path, { method: 'DELETE', headers: Auth.headers() });
    if (r.status === 401) { Auth.clear(); location.reload(); }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  },
  // Stream NDJSON from POST /run, calling onEvent per line.
  async stream(path, body, onEvent) {
    const r = await fetch('/api' + path, { method: 'POST', headers: Auth.headers(), body: JSON.stringify(body || {}) });
    if (!r.ok) throw new Error('run failed: ' + r.status);
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
        if (line) onEvent(JSON.parse(line));
      }
    }
  }
};
