# network-mgmt-platform — Install Notes & Improvement Analysis
Deployed on Linux-Test (10.11.58.115). Coexists with aruba-cx-troubleshooter.
Ports: frontend 80, postgres 5432, redis 6379 (aruba uses 3000/8443/8000/514 — no overlap).

## 1. Blockers fixed to make it build & run (were fatal as shipped)
- **No package-lock.json** but Dockerfiles used `npm ci` → switched to `npm install`.
- **Frontend Docker build context** mismatch (`context: ./frontend` vs `COPY frontend/…`/`COPY nginx/…`) → context set to repo root.
- **`snmp-native@^2.0.1` does not exist** → pinned to `^1.2.0`.
- **`config/database.js` exported `{sequelize,…}`** but `server.js`/`models` used it as the instance → export the instance; also honor `DATABASE_URL` (was ignored → dialed `localhost`).
- **`routes/devices.js` imported the auth middleware object** as a function → `const { auth }`.
- **Protocol modules default-exported** but consumers used `{ SSHManager }` → named exports; added `SSHManager.executeCommand` alias.
- **Static service methods destructured** (`{ discoverNetwork }`) lost `this` → bound exports.
- **`monitoring.js` used `ping` without importing it.**
- **`MonitoringResult` model referenced but never defined** → added.
- **Frontend**: missing `index.html`, `main.jsx` never wrapped `AuthProvider`, 3 imported pages missing, wrong `@mui/icons-material` names, malformed JSX in `Dashboard.jsx`, and missing `@emotion/*` peer deps → all fixed.
- **`01-init.sql`** started with `#` (invalid SQL) and inserted before tables existed → replaced with idempotent admin seeding at backend startup.
- **Worker startup race** (queried before schema existed) → `waitForSchema()`; disabled worker's HTTP healthcheck (it runs no web server).

## 2. Optimizations (existing code)
- **Search/filter is done in JS after `findAll()`** (routes `/` and `/search/:term`) — push down to SQL with `Op.iLike`; add indexes on `ip_address`, `status`, `vendor`. Add pagination (limit/offset + total).
- **Redis is deployed but never used.** Use it: cache device/stat reads; replace the worker's `setInterval` with a real queue/scheduler (BullMQ) for persistence, distributed locking, and retries (current design duplicates work if scaled and loses schedule on restart).
- **Discovery `pingSweep` only supports /24** (hardcoded) — other prefixes silently return `[]`. The repo already depends on `ip`/`ipaddr.js`; use them to expand arbitrary CIDR.
- **Discovery SNMP probing is sequential** per-IP/per-community; apply the same bounded concurrency the monitoring service uses.
- **`sequelize.sync({ alter: true })` on every boot** — slow and risky; move to migrations (umzug/sequelize-cli).
- **`console.log` everywhere** — use a structured logger (pino) with levels.
- **Docker**: backend runs as root; add non-root `USER`, a `.dockerignore` (frontend context now ships the whole repo), and split dev (bind-mount) vs prod (COPY) compose files. Remove deprecated `@mui/styles`.

## 3. Security (prioritize)
- **Device credentials are bcrypt-hashed (one-way) then used as the SSH/Telnet password** — they can never authenticate to a real device, and the `execute-command` "decrypt" (`bcrypt.compare(x,x)`) is a no-op. Use reversible authenticated encryption (AES-256-GCM) with a key from a secret manager.
- **`POST /api/auth/register` is public and lets the caller pick `role`** → privilege escalation (anyone becomes admin). Restrict role to admins; gate/close open registration.
- **Admin RBAC middleware exists but is never applied.** Require admin on `execute-command`, `config`, `delete`, `discover`.
- **CORS is fully open**; restrict origins.
- **JWT**: weak default secret fallbacks (fail closed instead), 1h token with no refresh/revocation; the `Session` model is unused. Add refresh/rotation.
- **No rate limiting / input validation** — add express-rate-limit + Joi/express-validator.
- **Postgres/Redis are published on 0.0.0.0** (5432/6379). Bind to the internal docker network / localhost only.
- **No audit log** for device command execution.

## 4. Additions (features to improve it)
- **Wire the frontend to the real backend** — `AuthContext`/`Login` are mock (accept any creds); `Devices/Monitoring/Discovery` are stubs. axios is already a dep.
- **Config backup & versioning** (the original code hints at a `ConfigBackup` model) with scheduled pulls + diffs.
- **Historical metrics & charts** — monitoring already collects CPU/mem/interfaces but persists almost nothing; store time series and render trends (chart.js is a dep). Consider a Prometheus exporter / Timescale for scale.
- **Alerting** — thresholds + email/Slack/webhook on device-down or high utilization.
- **Live updates** — `socket.io-client` is a frontend dep but there's no server socket; push monitoring events over WebSocket.
- **SNMPv3** (auth/priv); also fix the version mapping (`'2c'` string vs numeric).
- **OpenAPI/Swagger**, request IDs, and an app `/metrics` endpoint.
- **Tests + CI** — only two thin test files today.
