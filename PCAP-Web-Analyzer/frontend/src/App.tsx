import React, { useEffect, useState, useCallback } from 'react';

const API = '/api';
const tok = () => localStorage.getItem('pcap_token') || '';
const setTok = (t) => (t ? localStorage.setItem('pcap_token', t) : localStorage.removeItem('pcap_token'));

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const t = tok();
  if (t) headers['Authorization'] = `Bearer ${t}`;
  return fetch(API + path, { ...opts, headers });
}
async function apiJson(path, opts) {
  const r = await api(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
}
function formatBytes(b) {
  if (!b) return '0 B';
  const k = 1024, s = ['B', 'KB', 'MB', 'GB', 'TB'], i = Math.floor(Math.log(b) / Math.log(k));
  return parseFloat((b / Math.pow(k, i)).toFixed(2)) + ' ' + s[i];
}
function BarChart({ data, unit }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  if (!data.length) return <p className="muted">No data.</p>;
  return <div>{data.map((d) => (
    <div className="bar-row" key={d.label}>
      <div title={d.label} style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.label}</div>
      <div className="bar-track"><div className="bar-fill" style={{ width: `${(d.value / max) * 100}%` }} /></div>
      <div style={{ textAlign: 'right' }}>{unit === 'bytes' ? formatBytes(d.value) : d.value}</div>
    </div>))}</div>;
}
const Stat = ({ n, l, color }) => (
  <div className="stat"><div className="n" style={color ? { color } : {}}>{n}</div><div className="l">{l}</div></div>);
function Table({ cols, rows }) {
  if (!rows.length) return <p className="muted">None.</p>;
  return <div className="table-wrap"><table>
    <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
    <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
  </table></div>;
}

function Login({ onLogin }) {
  const [u, setU] = useState(''); const [p, setP] = useState(''); const [err, setErr] = useState('');
  const go = async () => {
    try {
      const fd = new FormData(); fd.append('username', u); fd.append('password', p);
      const r = await fetch(`${API}/auth/login`, { method: 'POST', body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Login failed');
      setTok(d.token); onLogin(d);
    } catch (e) { setErr(String(e.message || e)); }
  };
  return <div className="app"><div className="card login">
    <h2>Sign in</h2>
    <label className="field">Username<input value={u} onChange={(e) => setU(e.target.value)} /></label>
    <label className="field" style={{ marginTop: 8 }}>Password
      <input type="password" value={p} onChange={(e) => setP(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && go()} /></label>
    {err && <div className="alert">{err}</div>}
    <button style={{ marginTop: 12 }} onClick={go}>Sign in</button>
  </div></div>;
}

export default function App() {
  const [authEnabled, setAuthEnabled] = useState(false);
  const [user, setUser] = useState(null);
  const [tab, setTab] = useState('analyze');
  const [history, setHistory] = useState([]);

  const [files, setFiles] = useState([]);
  const [dedup, setDedup] = useState('content');
  const [win, setWin] = useState(0);
  const [resumable, setResumable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [upErr, setUpErr] = useState('');
  const [progress, setProgress] = useState('');

  const [jobId, setJobId] = useState(null);
  const [job, setJob] = useState(null);
  const [packets, setPackets] = useState({ total: 0, packets: [] });
  const [page, setPage] = useState(0);
  const [proto, setProto] = useState('');
  const [filter, setFilter] = useState('');
  const [appliedFilter, setAppliedFilter] = useState('');
  const [includeDups, setIncludeDups] = useState(true);
  const [savedFilters, setSavedFilters] = useState([]);
  const [shareUrl, setShareUrl] = useState('');
  const pageSize = 50;

  useEffect(() => {
    fetch(`${API}/auth/config`).then((r) => r.json()).then((d) => {
      setAuthEnabled(d.auth_enabled);
      if (!d.auth_enabled) setUser({ username: 'public', is_admin: true });
      else if (tok()) api('/auth/me').then((r) => r.ok ? r.json().then(setUser) : setTok(''));
    });
  }, []);

  const loadHistory = useCallback(async () => {
    try { setHistory((await apiJson('/jobs')).jobs || []); } catch {}
  }, []);
  const loadFilters = useCallback(async () => {
    try { setSavedFilters((await apiJson('/filters')).filters || []); } catch {}
  }, []);
  useEffect(() => { if (user) { loadHistory(); loadFilters(); } }, [user, loadHistory, loadFilters]);

  useEffect(() => {
    if (!jobId) return; let stop = false;
    const tick = async () => {
      try {
        const j = await apiJson(`/jobs/${jobId}`);
        if (stop) return; setJob(j);
        if (j.status === 'done' || j.status === 'error') { loadHistory(); return; }
        setTimeout(tick, 600);
      } catch {}
    };
    tick(); return () => { stop = true; };
  }, [jobId, loadHistory]);

  const loadPackets = useCallback(async () => {
    if (!jobId || !job || job.status !== 'done') return;
    const q = new URLSearchParams({ offset: String(page * pageSize), limit: String(pageSize), include_dups: String(includeDups) });
    if (proto) q.set('proto', proto);
    if (appliedFilter) q.set('filter', appliedFilter);
    try { setPackets(await apiJson(`/jobs/${jobId}/packets?${q}`)); }
    catch (e) { setUpErr(String(e.message || e)); }
  }, [jobId, job, page, proto, includeDups, appliedFilter]);
  useEffect(() => { loadPackets(); }, [loadPackets]);

  const uploadResumable = async (file) => {
    const { upload_id } = await apiJson('/uploads/init', { method: 'POST', body: (() => { const f = new FormData(); f.append('filename', file.name); return f; })() });
    const size = 4 * 1024 * 1024;
    for (let o = 0; o < file.size; o += size) {
      setProgress(`Uploading ${Math.min(100, Math.round((o / file.size) * 100))}%`);
      await api(`/uploads/${upload_id}/chunk`, { method: 'POST', body: file.slice(o, o + size) });
    }
    setProgress('Assembling…');
    return apiJson(`/uploads/${upload_id}/complete?dedup=${dedup}`, { method: 'POST' });
  };

  const upload = async () => {
    if (!files.length) { setUpErr('Select at least one pcap file.'); return; }
    setUpErr(''); setBusy(true); setJob(null); setShareUrl(''); setPackets({ total: 0, packets: [] });
    setPage(0); setAppliedFilter(''); setFilter('');
    try {
      let data;
      if (resumable) { data = await uploadResumable(files[0]); }
      else {
        const fd = new FormData(); files.forEach((f) => fd.append('files', f));
        data = await apiJson(`/upload?${new URLSearchParams({ dedup, time_window: String(win) })}`, { method: 'POST', body: fd });
      }
      setJobId(data.job_id);
    } catch (e) { setUpErr(String(e.message || e)); }
    finally { setBusy(false); setProgress(''); }
  };

  const openJob = (id) => { setJobId(id); setJob(null); setPage(0); setShareUrl(''); setAppliedFilter(''); setFilter(''); setPackets({ total: 0, packets: [] }); setTab('analyze'); };
  const del = async (id, e) => { e.stopPropagation(); await api(`/jobs/${id}`, { method: 'DELETE' }); if (id === jobId) { setJobId(null); setJob(null); } loadHistory(); };
  const downloadBlob = async (path, name) => {
    const r = await api(path); const b = await r.blob(); const url = URL.createObjectURL(b);
    const a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
  };
  const openReport = async () => {
    const r = await api(`/jobs/${jobId}/report`); const html = await r.text();
    const w = window.open('', '_blank'); if (w) { w.document.write(html); w.document.close(); }
  };
  const share = async () => {
    const d = await apiJson(`/jobs/${jobId}/share`, { method: 'POST' });
    setShareUrl(`${location.origin}${API}/shared/${d.share_token}/report`);
  };
  const applyFilter = () => { setPage(0); setAppliedFilter(filter); };
  const saveFilter = async () => {
    if (!filter.trim()) return;
    await apiJson('/filters', { method: 'POST', body: JSON.stringify({ name: filter.slice(0, 30), expression: filter }), headers: { 'Content-Type': 'application/json' } });
    loadFilters();
  };

  if (authEnabled && !user) return <Login onLogin={setUser} />;

  const s = job && job.summary;
  const det = s && s.detections;
  const totalPages = Math.ceil(packets.total / pageSize) || 1;
  const doneJobs = history.filter((h) => h.status === 'done');

  return (
    <div className="app">
      <div className="topbar">
        <div><h1>PCAP Analyzer</h1><p className="muted" style={{ margin: 0 }}>Dedup · protocol analysis · JA3 · threat-intel · detections</p></div>
        {authEnabled && user && <div className="row"><span className="pill">{user.username}{user.is_admin ? ' · admin' : ''}</span>
          <button className="ghost" onClick={() => { setTok(''); setUser(null); }}>Sign out</button></div>}
      </div>

      <div className="tabs">
        {['analyze', 'diff', 'threat-intel', 'capture'].map((t) => (
          <div key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {t === 'analyze' ? 'Analyze' : t === 'diff' ? 'Compare' : t === 'threat-intel' ? 'Threat Intel' : 'Live Capture'}</div>))}
      </div>

      {tab === 'analyze' && <>
        <div className="card">
          <h2>Upload captures</h2>
          <div className="row">
            <input type="file" multiple={!resumable} accept=".pcap,.pcapng,.cap" onChange={(e) => setFiles(Array.from(e.target.files))} />
            <label className="field">Dedup<select value={dedup} onChange={(e) => setDedup(e.target.value)}>
              <option value="content">Content</option><option value="none">None</option></select></label>
            <label className="field">Window (s)<input type="number" min="0" step="0.1" value={win} style={{ width: 80 }}
              onChange={(e) => setWin(parseFloat(e.target.value) || 0)} disabled={dedup === 'none'} /></label>
            <label className="field">&nbsp;<span><input type="checkbox" checked={resumable} onChange={(e) => setResumable(e.target.checked)} /> resumable (1 file)</span></label>
            <button onClick={upload} disabled={busy || !files.length}>{busy ? (progress || 'Uploading…') : 'Analyze'}</button>
          </div>
          {upErr && <div className="alert">{upErr}</div>}
        </div>

        {job && <div className="card">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2 style={{ margin: 0 }}>Results <span className={`status-pill ${job.status}`}>{job.status}</span></h2>
            {job.status === 'done' && <div className="row">
              <button className="ghost" onClick={openReport}>Report</button>
              <button className="ghost" onClick={() => downloadBlob(`/jobs/${jobId}/download?format=json`, `pcap_${jobId}.json`)}>JSON</button>
              <button className="ghost" onClick={() => downloadBlob(`/jobs/${jobId}/download?format=csv`, `pcap_${jobId}.csv`)}>CSV</button>
              <button className="ghost" onClick={share}>Share</button>
            </div>}
          </div>
          {job.status === 'processing' && <p className="muted">Processed {job.processed_packets} packets…</p>}
          {job.status === 'error' && <div className="alert">{job.error}</div>}
          {shareUrl && <div className="detbox">Public report: <code className="mono">{shareUrl}</code></div>}

          {s && <>
            <div className="stats" style={{ marginTop: 12 }}>
              <Stat n={s.total_packets} l="Total packets" />
              <Stat n={s.unique_packets} l="Unique" color="var(--good)" />
              <Stat n={s.duplicates_removed} l="Duplicates" color="var(--warn)" />
              <Stat n={s.ioc_hits.length} l="IOC hits" color={s.ioc_hits.length ? 'var(--bad)' : undefined} />
              <Stat n={(det.port_scans.length + det.beacons.length)} l="Detections" color={(det.port_scans.length + det.beacons.length) ? 'var(--warn)' : undefined} />
              <Stat n={s.http_transactions.length} l="HTTP txns" />
            </div>

            {(s.ioc_hits.length > 0 || det.port_scans.length > 0 || det.beacons.length > 0 || s.expert_info.length > 0) && <>
              <h3>Security findings</h3>
              {s.ioc_hits.map((h, i) => <div key={'i' + i} className="detbox bad">🚩 IOC match ({h.type}): <code className="mono">{h.indicator}</code></div>)}
              {det.port_scans.map((d, i) => <div key={'s' + i} className="detbox">🔍 Port scan from <code className="mono">{d.src}</code> — {d.distinct_ports} ports / {d.distinct_hosts} hosts ({d.kind})</div>)}
              {det.beacons.map((d, i) => <div key={'b' + i} className="detbox">📡 Beacon {d.src} → {d.dst}:{d.dport} — {d.hits} hits every ~{d.interval_s}s (regularity {d.regularity})</div>)}
              {s.expert_info.map((e, i) => <div key={'e' + i} className="detbox">⚠️ {e.label}: {e.count}</div>)}
            </>}

            <div className="grid2" style={{ marginTop: 8 }}>
              <div><h3>Protocol distribution</h3><BarChart data={Object.entries(s.protocol_distribution).map(([l, v]) => ({ label: l.toUpperCase(), value: v }))} /></div>
              <div><h3>Top talkers {s.geoip_enabled ? '' : ''}</h3><BarChart unit="bytes" data={s.top_talkers.map((t) => ({ label: t.host + (t.geo ? ` (${t.geo.country || ''})` : ''), value: t.bytes }))} /></div>
            </div>
            <div className="grid2">
              <div><h3>Top DNS queries</h3><BarChart data={s.dns_queries.map((d) => ({ label: d.name, value: d.count }))} /></div>
              <div><h3>TLS servers (SNI)</h3><BarChart data={s.tls_servers.map((d) => ({ label: d.server, value: d.count }))} /></div>
            </div>

            {s.ja3_fingerprints.length > 0 && <><h3>JA3 fingerprints</h3>
              <Table cols={['JA3', 'SNI', 'Count']} rows={s.ja3_fingerprints.map((j) => [<code className="mono">{j.ja3}</code>, j.sni || '', j.count])} /></>}

            {s.conversations.length > 0 && <><h3>Top conversations</h3>
              <Table cols={['Endpoint A', 'Endpoint B', 'Proto', 'Packets', 'Bytes']} rows={s.conversations.map((c) => [c.endpoints[0], c.endpoints[1], c.proto, c.packets, formatBytes(c.bytes)])} /></>}

            {s.http_transactions.length > 0 && <><h3>HTTP transactions</h3>
              <Table cols={['Kind', 'Method/Status', 'Host', 'URI/Type', 'Flow']} rows={s.http_transactions.map((h) => [h.kind, h.method || h.status, h.host || '', h.uri || h.content_type || '', `${h.src}:${h.sport}→${h.dst}:${h.dport}`])} /></>}

            {s.extracted_objects && s.extracted_objects.length > 0 && <><h3>Extracted objects</h3>
              <Table cols={['SHA-256', 'Type', 'Bytes', 'Flow']} rows={s.extracted_objects.map((o) => [<code className="mono">{o.sha256.slice(0, 16)}</code>, o.content_type || '', o.length, o.flow])} /></>}

            <h3>Packets</h3>
            <div className="row" style={{ marginBottom: 8 }}>
              <input placeholder='filter e.g. proto == TCP and dport == 443' value={filter} style={{ flex: 1, minWidth: 260 }}
                onChange={(e) => setFilter(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && applyFilter()} />
              <button className="ghost" onClick={applyFilter}>Apply</button>
              <button className="ghost" onClick={saveFilter}>Save</button>
              {savedFilters.length > 0 && <select value="" onChange={(e) => { setFilter(e.target.value); setAppliedFilter(e.target.value); setPage(0); }}>
                <option value="">Saved…</option>{savedFilters.map((f) => <option key={f.id} value={f.expression}>{f.name}</option>)}</select>}
              <label className="field">Proto<select value={proto} onChange={(e) => { setProto(e.target.value); setPage(0); }}>
                <option value="">All</option>{['dns', 'http', 'tls', 'icmp', 'arp', 'dhcp'].map((p) => <option key={p} value={p}>{p.toUpperCase()}</option>)}</select></label>
              <label className="field">&nbsp;<span><input type="checkbox" checked={includeDups} onChange={(e) => { setIncludeDups(e.target.checked); setPage(0); }} /> dups</span></label>
            </div>
            <div className="table-wrap"><table>
              <thead><tr><th>#</th><th>Time</th><th>Source</th><th>Dest</th><th>Proto</th><th>Sport</th><th>Dport</th><th>Len</th><th>Detected</th></tr></thead>
              <tbody>{packets.packets.map((p) => <tr key={p.idx} className={p.is_dup ? 'dup' : ''}>
                <td>{p.idx}</td><td>{p.ts ? p.ts.toFixed(3) : ''}</td><td>{p.src}</td><td>{p.dst}</td><td>{p.proto}</td>
                <td>{p.sport || ''}</td><td>{p.dport || ''}</td><td>{p.length}</td>
                <td>{p.protocols.map((t) => <span key={t} className={`tag ${t}`}>{t}</span>)}{p.is_dup ? <span className="tag">dup</span> : ''}</td></tr>)}</tbody>
            </table></div>
            <div className="pager">
              <button className="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Prev</button>
              <span className="muted">Page {page + 1}/{totalPages} · {packets.total} rows</span>
              <button className="ghost" disabled={page + 1 >= totalPages} onClick={() => setPage(page + 1)}>Next</button>
            </div>
          </>}
        </div>}
      </>}

      {tab === 'diff' && <DiffTab jobs={doneJobs} />}
      {tab === 'threat-intel' && <IocTab isAdmin={!authEnabled || (user && user.is_admin)} />}
      {tab === 'capture' && <CaptureTab onStarted={(id) => openJob(id)} />}

      <div className="card">
        <h2>History</h2>
        {!history.length && <p className="muted">No analyses yet.</p>}
        {history.map((h) => <div key={h.id} className={`history-item ${h.id === jobId ? 'active' : ''}`} onClick={() => openJob(h.id)}>
          <div><strong>{h.filenames.join(', ') || h.id}</strong>
            <div className="muted" style={{ fontSize: 12 }}>{new Date(h.created * 1000).toLocaleString()} · {h.total_packets} pkts · {h.unique_packets} unique · {h.source}{h.share_token ? ' · shared' : ''}</div></div>
          <div className="row"><span className={`status-pill ${h.status}`}>{h.status}</span>
            <button className="danger" onClick={(e) => del(h.id, e)}>Delete</button></div>
        </div>)}
      </div>
    </div>
  );
}

function DiffTab({ jobs }) {
  const [a, setA] = useState(''); const [b, setB] = useState(''); const [res, setRes] = useState(null); const [err, setErr] = useState('');
  const run = async () => {
    setErr(''); setRes(null);
    try { setRes(await apiJson(`/diff?a=${a}&b=${b}`)); } catch (e) { setErr(String(e.message || e)); }
  };
  const opt = (h) => <option key={h.id} value={h.id}>{(h.filenames.join(',') || h.id).slice(0, 40)}</option>;
  return <div className="card"><h2>Compare two captures</h2>
    <div className="row">
      <label className="field">Capture A<select value={a} onChange={(e) => setA(e.target.value)}><option value="">—</option>{jobs.map(opt)}</select></label>
      <label className="field">Capture B<select value={b} onChange={(e) => setB(e.target.value)}><option value="">—</option>{jobs.map(opt)}</select></label>
      <button onClick={run} disabled={!a || !b || a === b}>Compare</button>
    </div>
    {err && <div className="alert">{err}</div>}
    {res && <><div className="stats" style={{ marginTop: 12 }}>
      <Stat n={res.a_unique} l="A unique" /><Stat n={res.b_unique} l="B unique" />
      <Stat n={res.only_in_a} l="Only in A" color="var(--warn)" /><Stat n={res.only_in_b} l="Only in B" color="var(--warn)" />
      <Stat n={res.common} l="Common" color="var(--good)" /><Stat n={`${(res.similarity * 100).toFixed(1)}%`} l="Similarity" />
    </div>
    <div className="grid2"><div><h3>Sample only in A</h3>
      <Table cols={['#', 'Src', 'Dst', 'Proto', 'Len']} rows={res.sample_only_a.map((p) => [p.idx, p.src, p.dst, p.proto, p.length])} /></div>
      <div><h3>Sample only in B</h3>
        <Table cols={['#', 'Src', 'Dst', 'Proto', 'Len']} rows={res.sample_only_b.map((p) => [p.idx, p.src, p.dst, p.proto, p.length])} /></div></div></>}
  </div>;
}

function IocTab({ isAdmin }) {
  const [text, setText] = useState(''); const [msg, setMsg] = useState('');
  useEffect(() => { apiJson('/settings/iocs').then((d) => setText(d.iocs || '')).catch(() => {}); }, []);
  const save = async () => {
    try { await apiJson('/settings/iocs', { method: 'PUT', body: JSON.stringify({ iocs: text }), headers: { 'Content-Type': 'application/json' } }); setMsg('Saved. Applies to new analyses.'); }
    catch (e) { setMsg(String(e.message || e)); }
  };
  return <div className="card"><h2>Threat-intel indicators (IOCs)</h2>
    <p className="muted">One indicator per line: IPs, CIDRs, or domains. Matched against packet IPs, DNS names and TLS SNI during analysis.</p>
    <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder={'evil.com\n45.83.0.0/16\n1.2.3.4'} disabled={!isAdmin} />
    {isAdmin ? <button style={{ marginTop: 10 }} onClick={save}>Save indicators</button> : <p className="muted">Read-only (admin required).</p>}
    {msg && <div className="detbox">{msg}</div>}
  </div>;
}

function CaptureTab({ onStarted }) {
  const [iface, setIface] = useState(''); const [pkts, setPkts] = useState(1000); const [secs, setSecs] = useState(30); const [err, setErr] = useState('');
  const start = async () => {
    setErr('');
    try {
      const fd = new FormData(); fd.append('interface', iface); fd.append('max_packets', String(pkts)); fd.append('max_seconds', String(secs));
      const d = await apiJson('/capture', { method: 'POST', body: fd }); onStarted(d.job_id);
    } catch (e) { setErr(String(e.message || e)); }
  };
  return <div className="card"><h2>Live capture</h2>
    <p className="muted">Capture live traffic on a host interface, then analyze it. Requires the server to run with ENABLE_LIVE_CAPTURE=true and CAP_NET_RAW.</p>
    <div className="row">
      <label className="field">Interface<input value={iface} placeholder="eth0 (blank = any)" onChange={(e) => setIface(e.target.value)} /></label>
      <label className="field">Max packets<input type="number" value={pkts} style={{ width: 100 }} onChange={(e) => setPkts(parseInt(e.target.value) || 0)} /></label>
      <label className="field">Max seconds<input type="number" value={secs} style={{ width: 100 }} onChange={(e) => setSecs(parseInt(e.target.value) || 0)} /></label>
      <button onClick={start}>Start capture</button>
    </div>
    {err && <div className="alert">{err}</div>}
  </div>;
}
