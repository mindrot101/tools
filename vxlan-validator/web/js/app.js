// ---------- helpers ----------
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const h = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const state = { meta: null, catalog: null, inv: null };

const NAV = [
  ['dashboard', 'Dashboard', '▦'], ['topology', 'Topology', '⧉'], ['discover', 'Discover', '◎'],
  ['connections', 'Connections', '⚿'], ['testsuite', 'Test Suite', '🗒'], ['testrunner', 'Test Runner', '▷'],
  ['history', 'History', '↺'], ['reports', 'Reports', '🖹'], ['settings', 'Settings', '⚙'],
];

function navList() {
  const admin = state.meta && state.meta.role === 'admin';
  return [
    ...NAV,
    ...(admin ? [['users', 'Users', '👥']] : []),
    ['guide', 'Guide', '❔'],
  ];
}

// ---------- login ----------
function showLogin(msg) {
  $('#app').classList.add('hidden');
  $('#login').classList.remove('hidden');
  if (msg) $('#login-err').textContent = msg;
}
async function tryLogin() {
  $('#login-err').textContent = '';
  const key = $('#in-apikey').value.trim();
  const user = $('#in-user').value.trim();
  const pass = $('#in-pass').value;
  try {
    if (key) { Auth.set('key', key); }
    else if (user && pass) {
      const r = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: user, password: pass }) });
      if (!r.ok) throw new Error('invalid credentials');
      Auth.set('token', (await r.json()).token);
    } else { throw new Error('enter an API key or username/password'); }
    await boot();
  } catch (e) { Auth.clear(); showLogin(e.message); }
}

// ---------- boot ----------
async function boot() {
  state.meta = await API.get('/meta');
  state.catalog = await API.get('/catalog');
  state.inv = await API.get('/inventory');
  $('#login').classList.add('hidden');
  $('#app').classList.remove('hidden');
  $('#side-executor').textContent = state.meta.default_executor;
  $('#top-executor').textContent = state.meta.default_executor + ' executor';
  buildNav();
  route(location.hash.slice(1) || 'dashboard');
}
function buildNav() {
  const nav = $('#nav'); nav.innerHTML = '';
  navList().forEach(([id, label, ico]) => {
    const a = h(`<a class="nav-item" href="#${id}"><span class="ico">${ico}</span>${label}</a>`);
    nav.appendChild(a);
  });
}
function route(page) {
  const list = navList();
  if (!list.find(n => n[0] === page)) page = 'dashboard';
  location.hash = page;
  document.querySelectorAll('.nav-item').forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + page));
  $('#crumb').textContent = (list.find(n => n[0] === page) || [])[1] || '';
  const v = $('#view'); v.innerHTML = '';
  (PAGES[page] || PAGES.dashboard)(v);
}
window.addEventListener('hashchange', () => route(location.hash.slice(1)));

// ---------- pages ----------
const PAGES = {};

PAGES.dashboard = async (v) => {
  v.appendChild(h(`<div><div class="h1">Dashboard</div><div class="sub">Fabric health at a glance. Last validation run summary.</div></div>`));
  const runs = (await API.get('/runs')).runs;
  const inv = state.inv;
  const tiles = h(`<div class="grid g4" style="margin-bottom:16px"></div>`);
  const counts = [['VTEPs', inv.vtep.length], ['VNIs', inv.vni.length], ['Tunnels', inv.tunnel.length], ['VSX pairs', inv.vsx_pair.length]];
  counts.forEach(([k, val]) => tiles.appendChild(h(`<div class="stat"><div class="k">${k}</div><div class="v">${val}</div></div>`)));
  v.appendChild(tiles);
  if (!runs.length) { v.appendChild(h(`<div class="card empty">No runs yet. Head to Test Runner to validate the fabric.</div>`)); return; }
  const last = runs[0], t = last.summary.totals;
  const c = h(`<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
    <div><b>${esc(last.label)}</b> <span class="muted">· ${new Date(last.started_at * 1000).toLocaleString()} · ${esc(last.executor)}</span></div>
    <div><span class="st pass">${last.summary.pass_pct}% pass</span></div></div></div>`);
  const grid = h(`<div class="grid g4"></div>`);
  grid.appendChild(h(`<div class="stat"><div class="k">Total</div><div class="v">${last.summary.total}</div></div>`));
  grid.appendChild(h(`<div class="stat pass"><div class="k">Pass</div><div class="v">${t.pass}</div></div>`));
  grid.appendChild(h(`<div class="stat warn"><div class="k">Warn</div><div class="v">${t.warn}</div></div>`));
  grid.appendChild(h(`<div class="stat fail"><div class="k">Fail</div><div class="v">${t.fail}</div></div>`));
  c.appendChild(grid); v.appendChild(c);
};

PAGES.topology = (v) => {
  v.appendChild(h(`<div><div class="h1">Topology</div><div class="sub">Discovered fabric inventory.</div></div>`));
  const inv = state.inv;
  const total = inv.vtep.length + inv.tunnel.length + inv.vni.length + inv.vsx_pair.length;
  const bar = h(`<div class="toolbar"><span class="muted">${total} items in inventory</span><span class="spacer"></span><button id="inv-clear" class="btn ghost sm" style="color:var(--fail)">Clear all inventory</button></div>`);
  v.appendChild(bar);
  $('#inv-clear', bar).onclick = async () => {
    if (!confirm('Remove ALL inventory (VTEPs, tunnels, VNIs, VSX pairs)? This clears the demo fabric so you can populate from real discovery. It will not re-seed on restart.')) return;
    try {
      await API.del('/inventory');
      state.inv = await API.get('/inventory');
      route('topology');
    } catch (e) { alert('Clear failed: ' + e.message); }
  };
  if (total === 0) { v.appendChild(h(`<div class="card empty">Inventory is empty. Use <b>Discover</b> to populate it from your fabric.</div>`)); return; }
  const mk = (title, items, render) => {
    const card = h(`<div class="card" style="margin-bottom:16px"><h3 style="margin:0 0 12px">${title} <span class="muted">(${items.length})</span></h3><div class="list"></div></div>`);
    const list = $('.list', card);
    items.forEach(it => list.appendChild(h(render(it))));
    return card;
  };
  v.appendChild(mk('VTEPs', inv.vtep, x => `<div class="rowcard"><div><b>${esc(x.id)}</b> <span class="mono">${esc(x.loopback)} · ${esc(x.dc)}</span></div><div class="mono">MTU ${x.mtu}${x.mtu < 9198 ? ' ⚠' : ''} · ${esc(x.model || '')}</div></div>`));
  v.appendChild(mk('Tunnels', inv.tunnel, x => `<div class="rowcard"><div><b>${esc(x.src)} → ${esc(x.dst)}</b></div><div class="mono">${esc(x.src_lo)} → ${esc(x.dst_lo)}</div></div>`));
  v.appendChild(mk('VNIs', inv.vni, x => `<div class="rowcard"><div><b>VNI ${x.vni}</b> <span class="muted">${esc(x.tenant)}</span></div><div class="mono">VLAN ${x.vlan} · ${esc(x.bum)}</div></div>`));
  v.appendChild(mk('VSX pairs', inv.vsx_pair, x => `<div class="rowcard"><div><b>${esc(x.id)}</b></div><div class="mono">${esc(x.primary)} + ${esc(x.secondary)} · anycast ${esc(x.anycast_lo)}</div></div>`));
};

PAGES.discover = (v) => {
  v.appendChild(h(`<div><div class="h1">Discover</div><div class="sub">Probe a seed switch and walk the static-VXLAN fabric. Read-only show-commands only.</div></div>`));
  const card = h(`<div class="card" style="margin-bottom:16px">
    <div class="grid g3">
      <div><label>Seed switch (mgmt IP / host)</label><input id="d-seed" value="10.0.10.11"></div>
      <div><label>Depth</label><select id="d-depth"><option value="seed">Seed only</option><option value="vsx">+ VSX peer</option><option value="peers">+ vxlan1 peers</option><option value="recursive" selected>Recursive walk</option></select></div>
      <div><label>Adapter</label><select id="d-adapter"><option value="simulated" selected>Simulated</option><option value="agent">Agent (SSH/REST)</option></select></div>
    </div>
    <div id="d-connrow" class="hidden" style="margin-top:12px"><label>Connection profile (required for Agent)</label><select id="d-conn"></select></div>
    <div style="margin-top:14px"><button id="d-run" class="btn primary">Run discovery</button></div>
    <div id="d-log" class="log hidden" style="margin-top:14px"></div></div>`);
  v.appendChild(card);
  const preview = h(`<div id="d-preview"></div>`); v.appendChild(preview);
  $('#d-adapter', card).onchange = async e => {
    const row = $('#d-connrow', card);
    if (e.target.value === 'agent') {
      const rows = (await API.get('/connections')).connections;
      $('#d-conn', card).innerHTML = rows.map(r => `<option value="${esc(r.name)}">${esc(r.name)} (${esc(r.host)})</option>`).join('') || '<option value="">no profiles — add one under Connections</option>';
      row.classList.remove('hidden');
    } else { row.classList.add('hidden'); }
  };
  $('#d-run', card).onclick = async () => {
    const log = $('#d-log', card); log.classList.remove('hidden'); log.textContent = 'walking…\n';
    try {
      const res = await API.post('/discover', { seed: $('#d-seed').value, depth: $('#d-depth').value, adapter: $('#d-adapter').value, connection: $('#d-conn', card) ? $('#d-conn', card).value : null });
      log.textContent = res.log.join('\n');
      renderPreview(preview, res.found);
    } catch (e) { log.textContent = 'error: ' + e.message; }
  };
};
function renderPreview(mount, found) {
  mount.innerHTML = '';
  const card = h(`<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><b>Discovered</b><button id="imp" class="btn primary sm">Import selected</button></div><div class="list"></div></div>`);
  const list = $('.list', card);
  const sel = {};
  ['vtep', 'tunnel', 'vni', 'vsx_pair'].forEach(kind => (found[kind] || []).forEach(it => {
    const id = kind + ':' + it.id; sel[id] = true;
    const badge = it._new ? '<span class="tag">new</span>' : '<span class="tag exists">exists</span>';
    const row = h(`<label class="rowcard sel"><span class="check"><input type="checkbox" checked><b>${esc(it.id)}</b> <span class="mono">${kind}</span></span>${badge}</label>`);
    $('input', row).onchange = e => { sel[id] = e.target.checked; row.classList.toggle('sel', e.target.checked); };
    list.appendChild(row);
  }));
  $('#imp', card).onclick = async () => {
    const payload = {};
    ['vtep', 'tunnel', 'vni', 'vsx_pair'].forEach(kind => { payload[kind] = (found[kind] || []).filter(it => sel[kind + ':' + it.id]); });
    const r = await API.post('/inventory/import', payload);
    state.inv = await API.get('/inventory');
    $('#imp', card).textContent = `Imported ${r.imported} ✓`;
  };
  mount.appendChild(card);
}

PAGES.connections = (v) => {
  v.appendChild(h(`<div><div class="h1">Connections</div><div class="sub">Device access profiles for SSH/REST executors. Credentials are stored server-side, never returned to the browser.</div></div>`));
  const form = h(`<div class="card" style="margin-bottom:16px"><div class="grid g3">
    <div><label>Profile name</label><input id="c-name" placeholder="e.g. core1" autocomplete="off"></div>
    <div><label>Host / mgmt IP</label><input id="c-host" placeholder="e.g. 10.11.58.180" autocomplete="off"></div>
    <div><label>Protocol</label><select id="c-proto"><option>ssh</option><option>rest</option></select></div>
    <div><label>Username</label><input id="c-user" autocomplete="off"></div>
    <div><label>Password</label><input id="c-pass" type="password" autocomplete="new-password"></div>
    <div><label>Mgmt VRF</label><input id="c-vrf" value="mgmt"></div>
    </div><div style="margin-top:14px"><button id="c-save" class="btn primary">Save profile</button> <span id="c-msg" class="muted"></span></div></div>`);
  v.appendChild(form);
  const listCard = h(`<div class="card"><b>Saved profiles</b><div class="list" style="margin-top:12px"></div></div>`);
  v.appendChild(listCard);
  const refresh = async () => {
    const rows = (await API.get('/connections')).connections;
    const list = $('.list', listCard); list.innerHTML = rows.length ? '' : '<div class="empty">No profiles yet.</div>';
    rows.forEach(r => {
      const row = h(`<div class="rowcard"><div><b>${esc(r.name) || '<span class="mono" style="color:var(--fail)">(no name)</span>'}</b> <span class="mono">${esc(r.host) || '(no host)'} · ${esc(r.protocol)} · vrf ${esc(r.vrf || '')}</span></div><div style="display:flex;gap:12px;align-items:center"><span class="mono">${esc(r.username || '')}</span><button class="btn ghost sm" style="color:var(--fail)">Delete</button></div></div>`);
      $('button', row).onclick = async () => {
        if (!confirm(`Delete connection profile "${r.name || '(no name)'}"?`)) return;
        await API.del('/connections/' + encodeURIComponent(r.name));
        refresh();
      };
      list.appendChild(row);
    });
  };
  $('#c-save', form).onclick = async () => {
    const name = $('#c-name').value.trim(), host = $('#c-host').value.trim();
    if (!name || !host) { $('#c-msg', form).textContent = 'Profile name and host are both required.'; return; }
    try {
      await API.post('/connections', { name, host, protocol: $('#c-proto').value, username: $('#c-user').value, password: $('#c-pass').value, vrf: $('#c-vrf').value });
      $('#c-msg', form).textContent = 'saved ✓';
      $('#c-name').value = ''; $('#c-host').value = ''; $('#c-user').value = ''; $('#c-pass').value = '';
      refresh();
    } catch (e) { $('#c-msg', form).textContent = e.message; }
  };
  refresh();
};

PAGES.testsuite = (v) => {
  v.appendChild(h(`<div><div class="h1">Test Suite</div><div class="sub">${state.catalog.count} read-only checks across ${state.catalog.categories.length} categories. Full stack: physical → underlay → MTU → overlay → VSX.</div></div>`));
  state.catalog.categories.forEach(cat => {
    const tests = state.catalog.tests.filter(t => t.category === cat);
    const group = h(`<div class="tgroup"><h3>🗒 ${esc(cat)}</h3><div class="cnt">${tests.length} test${tests.length > 1 ? 's' : ''}</div><div class="grid g2"></div></div>`);
    const g = $('.grid', group);
    tests.forEach(t => {
      const rest = t.rest && t.rest.length ? `<div class="cli" style="margin-top:8px"><span class="lbl">◉ REST (AOS-CX v10.x)</span>${esc(t.rest.join('\n'))}</div>` : '';
      g.appendChild(h(`<div class="tcard"><div class="thead"><div><div class="tt">${esc(t.title)}</div><div class="scope">Scope: ${esc(t.scope)}</div></div><span class="sev ${t.severity}">${t.severity.toUpperCase()}</span></div>
        <div class="desc">${esc(t.description)}</div>
        <div class="cli"><span class="lbl">›_ CLI</span>${esc(t.cli.map(c => 'switch# ' + c).join('\n'))}</div>${rest}
        <div class="rem"><b>Remediation:</b> ${esc(t.remediation)}</div></div>`));
    });
    v.appendChild(group);
  });
};

PAGES.testrunner = (v) => {
  const inv = state.inv, cat = state.catalog;
  const selTests = new Set(cat.tests.map(t => t.id));
  const selT = { vteps: new Set(inv.vtep.map(x => x.id)), tunnels: new Set(inv.tunnel.map(x => x.id)), vnis: new Set(inv.vni.map(x => x.id)), vsxpairs: new Set(inv.vsx_pair.map(x => x.id)) };
  v.appendChild(h(`<div><div class="h1">Test Runner</div><div class="sub">Pick tests, pick targets, run validations. Results stream in below.</div></div>`));
  const bar = h(`<div class="toolbar"><span class="spacer"></span><label style="margin:0">Executor</label>
    <select id="r-exec" style="width:auto"><option value="simulated">Simulated</option><option value="ssh">SSH</option><option value="rest">REST</option></select>
    <select id="r-conn" style="width:auto" class="hidden"></select>
    <button id="r-run" class="btn primary">Run checks</button></div>`);
  v.appendChild(bar);
  const cols = h(`<div class="grid g2"></div>`);
  // tests column
  const tcol = h(`<div class="card"><div style="display:flex;justify-content:space-between;margin-bottom:10px"><b>Tests</b><div><span class="linklike" id="t-all">All</span> · <span class="linklike" id="t-none">None</span></div></div><div class="scroll list"></div></div>`);
  const tlist = $('.list', tcol);
  cat.tests.forEach(t => {
    const row = h(`<label class="rowcard sel"><span class="check"><input type="checkbox" checked><span><b>${esc(t.title)}</b><div class="mono">${esc(t.category)} · ${esc(t.scope)} · ${esc(t.severity)}</div></span></span></label>`);
    $('input', row).onchange = e => { e.target.checked ? selTests.add(t.id) : selTests.delete(t.id); row.classList.toggle('sel', e.target.checked); updatePlan(); };
    tlist.appendChild(row);
  });
  $('#t-all', tcol).onclick = () => { tlist.querySelectorAll('input').forEach(i => { i.checked = true; }); cat.tests.forEach(t => selTests.add(t.id)); tlist.querySelectorAll('.rowcard').forEach(r => r.classList.add('sel')); updatePlan(); };
  $('#t-none', tcol).onclick = () => { tlist.querySelectorAll('input').forEach(i => { i.checked = false; }); selTests.clear(); tlist.querySelectorAll('.rowcard').forEach(r => r.classList.remove('sel')); updatePlan(); };
  // targets column
  const gcol = h(`<div class="card"><div style="margin-bottom:10px"><b>Targets</b> <span class="muted" id="plan"></span></div><div class="scroll"></div></div>`);
  const gwrap = $('.scroll', gcol);
  const groups = [['VTEPs', 'vteps', inv.vtep, x => `${x.id} · ${x.loopback}`], ['Tunnels', 'tunnels', inv.tunnel, x => `${x.src} → ${x.dst}`], ['VNIs', 'vnis', inv.vni, x => `VNI ${x.vni} · VLAN ${x.vlan}`], ['VSX pairs', 'vsxpairs', inv.vsx_pair, x => x.id]];
  groups.forEach(([label, key, items, fmt]) => {
    gwrap.appendChild(h(`<div style="margin:6px 0 8px;font-weight:700">${label} <span class="muted">(${items.length})</span></div>`));
    const list = h(`<div class="list" style="margin-bottom:14px"></div>`);
    items.forEach(it => {
      const row = h(`<label class="rowcard sel"><span class="check"><input type="checkbox" checked><span class="mono">${esc(fmt(it))}</span></span></label>`);
      $('input', row).onchange = e => { e.target.checked ? selT[key].add(it.id) : selT[key].delete(it.id); row.classList.toggle('sel', e.target.checked); updatePlan(); };
      list.appendChild(row);
    });
    gwrap.appendChild(list);
  });
  cols.appendChild(tcol); cols.appendChild(gcol); v.appendChild(cols);
  // live results
  const live = h(`<div class="card" style="margin-top:16px"><div style="display:flex;justify-content:space-between;margin-bottom:8px"><b>Live results</b><span id="live-state" class="muted">Idle</span></div><div class="bar" id="live-bar"><i class="p" style="width:0"></i><i class="w" style="width:0"></i><i class="f" style="width:0"></i></div><div class="list scroll" id="live-list" style="margin-top:12px"><div class="empty">Select tests and targets, then press Run.</div></div></div>`);
  v.appendChild(live);

  function planCount() {
    let n = 0;
    cat.tests.forEach(t => { if (!selTests.has(t.id)) return; const map = { vtep: 'vteps', tunnel: 'tunnels', vni: 'vnis', vsxPair: 'vsxpairs' }[t.scope]; n += selT[map] ? selT[map].size : 0; });
    return n;
  }
  function updatePlan() { $('#plan', gcol).textContent = `${planCount()} planned checks`; $('#r-run', bar).textContent = `Run ${planCount()} checks`; }
  updatePlan();

  // executor -> connection picker
  const execSel = $('#r-exec', bar), connSel = $('#r-conn', bar);
  execSel.onchange = async () => {
    if (execSel.value === 'simulated') { connSel.classList.add('hidden'); return; }
    const rows = (await API.get('/connections')).connections;
    connSel.innerHTML = rows.map(r => `<option value="${esc(r.name)}">${esc(r.name)} (${esc(r.host)})</option>`).join('') || '<option value="">no profiles</option>';
    connSel.classList.remove('hidden');
  };

  $('#r-run', bar).onclick = async () => {
    const totals = { pass: 0, warn: 0, fail: 0, error: 0 }; let planned = planCount(), seen = 0;
    const list = $('#live-list', live); list.innerHTML = '';
    $('#live-state', live).textContent = 'Running…'; $('#r-run', bar).disabled = true;
    const targets = { vteps: [...selT.vteps], tunnels: [...selT.tunnels], vnis: [...selT.vnis], vsxpairs: [...selT.vsxpairs] };
    const body = { executor: execSel.value, tests: [...selTests], targets, label: 'Runner ' + new Date().toLocaleTimeString(), connection: connSel.value };
    try {
      await API.stream('/run', body, ev => {
        if (ev.type === 'result') {
          totals[ev.status] = (totals[ev.status] || 0) + 1; seen++;
          const row = h(`<div class="rowcard"><div><b>${esc(ev.title)}</b> <span class="mono">${esc(ev.target)}</span><div class="mono">${esc(ev.category)} · ${esc(ev.detail)}</div></div><span class="st ${ev.status}">${ev.status.toUpperCase()}</span></div>`);
          if (ev.status === 'pass') list.appendChild(row); else list.insertBefore(row, list.firstChild);
          const pct = k => planned ? (100 * totals[k] / planned) + '%' : '0';
          const b = $('#live-bar', live); b.children[0].style.width = pct('pass'); b.children[1].style.width = pct('warn'); b.children[2].style.width = pct('fail');
          $('#live-state', live).textContent = `${seen}/${planned} · ${totals.pass}P / ${totals.warn}W / ${totals.fail}F`;
        } else if (ev.type === 'done') {
          $('#live-state', live).textContent = `Done · ${ev.summary.pass_pct}% pass`;
        }
      });
    } catch (e) { $('#live-state', live).textContent = 'error: ' + e.message; }
    $('#r-run', bar).disabled = false;
  };
};

PAGES.history = async (v) => {
  v.appendChild(h(`<div><div class="h1">History</div><div class="sub">Every run is stored. Pick a run to review its results.</div></div>`));
  const runs = (await API.get('/runs')).runs;
  if (!runs.length) { v.appendChild(h(`<div class="card empty">No runs yet.</div>`)); return; }
  const cols = h(`<div class="grid g2"></div>`);
  const left = h(`<div class="card"><b>Runs</b><div class="muted" style="margin-bottom:10px">${runs.length} total</div><div class="list"></div></div>`);
  const right = h(`<div class="card" id="run-detail"><div class="empty">Select a run.</div></div>`);
  const list = $('.list', left);
  runs.forEach((r, i) => {
    const row = h(`<div class="rowcard ${i === 0 ? 'sel' : ''}"><div><b>${esc(r.label)}</b><div class="mono">${new Date(r.started_at * 1000).toLocaleString()} · ${esc(r.executor)}</div></div><span class="st pass">${r.summary.pass_pct}%</span></div>`);
    row.onclick = () => { list.querySelectorAll('.rowcard').forEach(x => x.classList.remove('sel')); row.classList.add('sel'); showRun(right, r.id); };
    list.appendChild(row);
  });
  cols.appendChild(left); cols.appendChild(right); v.appendChild(cols);
  showRun(right, runs[0].id);
};
async function showRun(mount, id) {
  const r = await API.get('/runs/' + id);
  const t = r.summary.totals;
  mount.innerHTML = '';
  mount.appendChild(h(`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><div><b>${esc(r.label)}</b> <span class="muted">· ${esc(r.executor)} · ${r.summary.total} checks</span></div></div>`));
  const grid = h(`<div class="grid g3" style="margin-bottom:14px"><div class="stat pass"><div class="k">Pass</div><div class="v">${t.pass}</div></div><div class="stat warn"><div class="k">Warn</div><div class="v">${t.warn}</div></div><div class="stat fail"><div class="k">Fail</div><div class="v">${t.fail}</div></div></div>`);
  mount.appendChild(grid);
  const problems = r.results.filter(x => x.status !== 'pass');
  const list = h(`<div class="list scroll"></div>`);
  if (!problems.length) list.appendChild(h(`<div class="empty">All checks passed.</div>`));
  problems.forEach(x => list.appendChild(h(`<div class="rowcard"><div><span class="mono">${esc(x.test_id)} · ${esc(x.target)}</span><div class="muted">${esc(x.detail)}</div></div><span class="st ${x.status}">${x.status.toUpperCase()}</span></div>`)));
  mount.appendChild(h(`<div style="margin-bottom:8px;font-weight:700">Findings (${problems.length})</div>`));
  mount.appendChild(list);
};

PAGES.reports = async (v) => {
  v.appendChild(h(`<div><div class="h1">Reports</div><div class="sub">Shareable summary of any validation run.</div></div>`));
  const runs = (await API.get('/runs')).runs;
  if (!runs.length) { v.appendChild(h(`<div class="card empty">No runs to report on yet.</div>`)); return; }
  const bar = h(`<div class="toolbar"><select id="rp-run" style="width:auto">${runs.map(r => `<option value="${r.id}">${new Date(r.started_at * 1000).toLocaleString()} — ${esc(r.label)}</option>`).join('')}</select><button id="rp-json" class="btn">Download JSON</button><button id="rp-print" class="btn">Print</button></div>`);
  v.appendChild(bar);
  const mount = h(`<div id="rp-body"></div>`); v.appendChild(mount);
  const render = async (id) => {
    const r = await API.get('/runs/' + id), t = r.summary.totals;
    mount.innerHTML = '';
    const card = h(`<div class="card"><h3 style="margin:0 0 12px">🖹 Executive summary</h3><div class="grid g4">
      <div class="stat"><div class="k">Total tests</div><div class="v">${r.summary.total}</div></div>
      <div class="stat pass"><div class="k">Pass</div><div class="v">${t.pass}</div></div>
      <div class="stat warn"><div class="k">Warn</div><div class="v">${t.warn}</div></div>
      <div class="stat fail"><div class="k">Fail</div><div class="v">${t.fail}</div></div></div>
      <div class="grid g4" style="margin-top:12px">
      <div class="stat"><div class="k">VTEPs</div><div class="v">${r.summary.vteps}</div></div>
      <div class="stat"><div class="k">Tunnels</div><div class="v">${r.summary.tunnels}</div></div>
      <div class="stat"><div class="k">VNIs</div><div class="v">${r.summary.vnis}</div></div>
      <div class="stat"><div class="k">Executor</div><div class="v" style="font-size:18px">${esc(r.executor)}</div></div></div></div>`);
    mount.appendChild(card);
    // Layer health: which elements are contributing an issue.
    const bc = r.summary.by_category || {};
    if (Object.keys(bc).length) {
      const order = { fail: 0, error: 1, warn: 2, pass: 3 };
      const cats = Object.keys(bc).sort((a, b) => (order[bc[a]] - order[bc[b]]) || a.localeCompare(b));
      const oh = r.summary.overall_health || 'healthy';
      const ohClass = oh === 'critical' ? 'fail' : (oh === 'degraded' ? 'warn' : 'pass');
      const lh = h(`<div class="card" style="margin-top:16px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><h3 style="margin:0">Layer health</h3><span class="st ${ohClass}">${esc(oh.toUpperCase())}</span></div><div class="grid g3"></div></div>`);
      const g = $('.grid', lh);
      cats.forEach(cat => {
        const s = bc[cat];
        g.appendChild(h(`<div class="rowcard"><b>${esc(cat)}</b><span class="st ${s}">${s.toUpperCase()}</span></div>`));
      });
      mount.appendChild(lh);
    }
  };
  $('#rp-run', bar).onchange = e => render(e.target.value);
  $('#rp-json', bar).onclick = async () => {
    const r = await API.get('/runs/' + $('#rp-run', bar).value);
    const blob = new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'vxlan-run-' + r.id + '.json'; a.click();
  };
  $('#rp-print', bar).onclick = () => window.print();
  render(runs[0].id);
};

PAGES.settings = async (v) => {
  v.appendChild(h(`<div><div class="h1">Settings</div><div class="sub">Deployment configuration and agent status. Read-only enforcement is not user-configurable.</div></div>`));
  const st = await API.get('/agent/status').catch(() => null);
  const c = h(`<div class="card" style="margin-bottom:16px"><h3 style="margin:0 0 12px">Deployment</h3></div>`);
  const kv = [['Version', state.meta.version], ['Mode', '🔒 Read-only — enforced in code'], ['Default executor', state.meta.default_executor], ['Auth', 'API key (primary) · local users ' + (state.meta.local_users ? 'available' : 'disabled')], ['Your role', state.meta.role]];
  kv.forEach(([k, val]) => c.appendChild(h(`<div class="kv"><span class="k">${esc(k)}</span><span>${esc(val)}</span></div>`)));
  v.appendChild(c);
  if (st) {
    const a = h(`<div class="card"><h3 style="margin:0 0 12px">Agent status</h3></div>`);
    [['Uptime', st.uptime_s + 's'], ['Guard blocks', st.guard_blocks], ['Switches in inventory', st.switches.length]].forEach(([k, val]) => a.appendChild(h(`<div class="kv"><span class="k">${esc(k)}</span><span>${esc(val)}</span></div>`)));
    a.appendChild(h(`<div style="margin:14px 0 8px;font-weight:700">Audit tail</div>`));
    const log = h(`<div class="log"></div>`);
    log.textContent = (st.audit_tail || []).map(x => `${x.iso}  ${x.event}`).join('\n') || 'no events';
    a.appendChild(log); v.appendChild(a);
  }
};

PAGES.users = async (v) => {
  v.appendChild(h(`<div><div class="h1">Users</div><div class="sub">Local accounts for username/password sign-in. Passwords are bcrypt-hashed; they are never stored or returned in plain text.</div></div>`));
  const form = h(`<div class="card" style="margin-bottom:16px"><div class="grid g3">
    <div><label>Username</label><input id="u-name" placeholder="e.g. jsmith" autocomplete="off"></div>
    <div><label>Password</label><input id="u-pass" type="password" autocomplete="new-password"></div>
    <div><label>Role</label><select id="u-role"><option value="viewer">viewer — read reports</option><option value="operator">operator — run tests + discover</option><option value="admin">admin — full control</option></select></div>
    </div><div style="margin-top:14px"><button id="u-save" class="btn primary">Add / update user</button> <span id="u-msg" class="muted"></span></div></div>`);
  v.appendChild(form);
  const listCard = h(`<div class="card"><b>Accounts</b><div class="list" style="margin-top:12px"></div></div>`);
  v.appendChild(listCard);
  const me = state.meta.user;
  const roleBadge = { admin: 'fail', operator: 'warn', viewer: 'pass' };
  const refresh = async () => {
    const users = (await API.get('/users')).users;
    const list = $('.list', listCard); list.innerHTML = users.length ? '' : '<div class="empty">No local users yet.</div>';
    users.forEach(u => {
      const isMe = u.username === me;
      const row = h(`<div class="rowcard"><div><b>${esc(u.username)}</b> ${isMe ? '<span class="tag">you</span>' : ''} <span class="mono">created ${new Date(u.created_at * 1000).toLocaleDateString()}</span></div>
        <div style="display:flex;gap:12px;align-items:center"><span class="st ${roleBadge[u.role] || 'pass'}">${esc(u.role)}</span><button class="btn ghost sm" style="color:var(--fail)" ${isMe ? 'disabled' : ''}>Delete</button></div></div>`);
      const btn = $('button', row);
      if (!isMe) btn.onclick = async () => {
        if (!confirm(`Delete user "${u.username}"?`)) return;
        try { await API.del('/users/' + encodeURIComponent(u.username)); refresh(); }
        catch (e) { alert(e.message); }
      };
      list.appendChild(row);
    });
  };
  $('#u-save', form).onclick = async () => {
    const username = $('#u-name').value.trim(), password = $('#u-pass').value;
    if (!username || !password) { $('#u-msg', form).textContent = 'Username and password are both required.'; return; }
    try {
      await API.post('/users', { username, password, role: $('#u-role').value });
      $('#u-msg', form).textContent = 'saved ✓'; $('#u-name').value = ''; $('#u-pass').value = '';
      refresh();
    } catch (e) { $('#u-msg', form).textContent = e.message; }
  };
  refresh();
};

PAGES.guide = (v) => {
  v.appendChild(h(`<div><div class="h1">Guide</div><div class="sub">How the VXLAN Validator works, and the workflow from demo to real fabric.</div></div>`));
  const card = (title, bodyHtml) => h(`<div class="card" style="margin-bottom:16px"><h3 style="margin:0 0 10px">${title}</h3>${bodyHtml}</div>`);

  v.appendChild(card('What this tool does', `
    <div class="rem">It validates a <b>static (non-EVPN)</b> VXLAN fabric on Aruba CX — walking the full stack:
    physical, L2/STP, underlay routing, <b>MTU (including mismatch detection)</b>, L4, VTEP config, tunnel state,
    VNI membership, MAC learning, head-end replication, data plane, QoS, hardware tables, ARP, and VSX.
    It runs <b>${state.catalog.count} checks across ${state.catalog.categories.length} categories</b> and never writes to a device.</div>`));

  v.appendChild(card('&#128274; Read-only, enforced in three layers', `
    <div class="rem">1. <b>Catalog</b> — every check only ever declares <span class="mono">show</span> / <span class="mono">ping</span> / <span class="mono">traceroute</span> and REST <span class="mono">GET</span>.<br>
    2. <b>Command guard</b> — parses every command before it leaves the container and blocks any write verb, chaining, redirection, or non-GET REST call.<br>
    3. <b>AOS-CX role</b> — the switch service account is authorized for read commands only (see the docs).<br>
    The read-only badge is always visible, and any blocked attempt is counted and written to the audit log.</div>`));

  v.appendChild(card('The workflow', `
    <div class="list">
      <div class="rowcard"><div><b>1 &middot; Sign in</b><div class="muted">API key (operator) or a local username/password. Admins can manage users and connection profiles.</div></div></div>
      <div class="rowcard"><div><b>2 &middot; Add a Connection</b> <span class="mono">Connections</span><div class="muted">Admin adds a device profile: name, switch mgmt IP, SSH/REST, service-account creds. Stored server-side, never returned to the browser.</div></div></div>
      <div class="rowcard"><div><b>3 &middot; Discover</b> <span class="mono">Discover</span><div class="muted">Pick a seed switch + the Agent adapter + your profile. It SSHes in read-only, parses the vxlan1 config / VSX / loopback, and walks the fabric. Review and Import the results.</div></div></div>
      <div class="rowcard"><div><b>4 &middot; Review Topology</b> <span class="mono">Topology</span><div class="muted">See the imported VTEPs, tunnels, VNIs, and VSX pairs. Use Clear all inventory here to drop the demo fabric before importing real gear.</div></div></div>
      <div class="rowcard"><div><b>5 &middot; Run checks</b> <span class="mono">Test Runner</span><div class="muted">Select tests and targets, choose the executor, and Run. Results stream live with pass / warn / fail.</div></div></div>
      <div class="rowcard"><div><b>6 &middot; Report</b> <span class="mono">Reports</span> <span class="mono">History</span><div class="muted">Every run is saved. Reports show the per-layer health rollup and export to JSON / print.</div></div></div>
    </div>`));

  v.appendChild(card('Executors', `
    <div class="rem"><b>Simulated</b> — a seeded demo fabric with a built-in MTU fault; needs no network, good for learning the UI.<br>
    <b>SSH</b> — Netmiko, read-only <span class="mono">show</span> commands only.<br>
    <b>REST</b> — AOS-CX REST v10.x, <span class="mono">GET</span> only, TLS-verified against a mounted CA bundle.<br>
    Switch the executor in the Test Runner (SSH/REST require a Connection profile).</div>`));

  v.appendChild(card('Roles', `
    <div class="list">
      <div class="rowcard"><b>viewer</b><span class="st pass">read reports &amp; inventory</span></div>
      <div class="rowcard"><b>operator</b><span class="st warn">run tests, discover, import, clear inventory</span></div>
      <div class="rowcard"><b>admin</b><span class="st fail">manage users &amp; connection profiles, read audit log</span></div>
    </div>
    <div class="rem" style="margin-top:10px">The API key maps to <b>operator</b>. To manage users/profiles, sign in as an <b>admin</b> local account.</div>`));

  v.appendChild(card('Layer health', `
    <div class="rem">Every element contributes to overall VXLAN health — even STP, since static VXLAN rides L2. Each run rolls the worst
    result per layer into a <b>HEALTHY / DEGRADED / CRITICAL</b> verdict on the Reports page, so an issue anywhere in the stack surfaces
    instead of getting lost in a long list. Findings name the specific element (e.g. a tunnel, a VTEP, an interface).</div>`));
};

// ---------- init ----------
$('#btn-login').onclick = tryLogin;
[$('#in-apikey'), $('#in-pass')].forEach(el => el.addEventListener('keydown', e => { if (e.key === 'Enter') tryLogin(); }));
$('#btn-logout').onclick = () => { Auth.clear(); location.reload(); };
(async () => { if (Auth.cred) { try { await boot(); } catch { showLogin(); } } else showLogin(); })();
