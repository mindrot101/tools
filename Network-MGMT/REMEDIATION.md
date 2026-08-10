# Remediation Status — "fix everything" pass (2026-08-09)

Fresh, non-root deployment on Linux-Test. DB/Redis now bound to 127.0.0.1 only; frontend on :80.
Tables: users, sessions, devices, monitoring_results, config_backups, alerts, audit_logs.

## DONE — Security
- Device credentials now use reversible **AES-256-GCM** (utils/crypto.js, ENCRYPTION_KEY). SSH/Telnet decrypt at connect. (was bcrypt one-way → unusable)
- **Registration is admin-only** + validated role → privilege-escalation closed. (verified: register w/o token = 401)
- **RBAC enforced**: read=any auth; create/update/health-check=admin|operator; delete/discover/execute/config=admin. (verified: operator delete/discover = 403, create = 201)
- **JWT** fail-closed on weak secret in production; configurable expiry (JWT_EXPIRES_IN, default 8h); /me and /change-password use the middleware.
- **CORS** restricted via CORS_ORIGIN; **helmet** retained.
- **Rate limiting** (global 300/min; login 20/15min) + **express-validator** on auth & device input.
- **Audit log** of user/device/network actions (audit_logs, GET /api/audit admin-only).
- Passwords never returned by the API (excluded attributes).
- DB/Redis published only on 127.0.0.1.

## DONE — Optimizations
- Device list/search pushed to **SQL** (Op.iLike) with **pagination** ({data,total,page,pages}) + **indexes** (status, vendor, ip_address, device_id, createdAt).
- **Redis** now used: caches stats/list (TTL) + **distributed locks** so worker cycles don't double-run; cache invalidated on writes.
- **Discovery** supports **arbitrary CIDR** (not just /24) with a host cap, and bounded concurrency (utils/concurrency.js).
- **SNMP version mapping** fixed (2c→1).
- **pino** structured logging + pino-http request logs.
- Backend image runs **non-root**; added **.dockerignore**; removed deprecated **@mui/styles**.

## DONE — Features
- **GET /api/devices/stats** + real Dashboard tiles.
- **Monitoring page**: run on-demand health checks (persisted to monitoring_results); **GET /:id/monitoring** history.
- **Discovery page**: run/import scans (admin).
- **Alerts**: alerts table + worker raises device_down / high_cpu; **GET /api/alerts**, ack; optional **ALERT_WEBHOOK_URL**; Alerts page.
- **Config backups**: GET /:id/config stores a hashed version in config_backups; **GET /:id/backups**.
- Frontend: real auth (login→JWT→/me), NavBar with role + logout, all pages wired to the API.


## Round 2 — previously-deferred items, now DONE (verified)
- **SNMPv3**: swapped snmp-native -> **net-snmp**; Device has snmp_user/security_level/auth+priv protocol & keys (keys AES-encrypted, never returned). UI Add-Device form exposes v1/v2c/v3. (verified: v3 device created 201, auth key encrypted in DB, 9 snmp_* columns)
- **Live updates (WebSocket)**: **socket.io** server + Redis pub/sub bridge (worker publishes -> backend re-emits), nginx `/socket.io` upgrade proxy, frontend live badge + auto-refresh on alert/monitoring. (verified: handshake via nginx returns a session)
- **SMTP email alerts**: **nodemailer**; sends on warning/critical when SMTP_HOST + ALERT_EMAIL_TO are set (inert otherwise). Webhook still supported.
- **OpenAPI/Swagger**: served at **/api/docs** (+ /api/openapi.json). (verified: 200)
- **Migration framework**: **umzug** runner + SequelizeMeta; baseline migration runs at startup. (verified: 1 migration applied)
- **Tests + CI**: mocha unit tests (crypto round-trip, CIDR expansion, RBAC) — **11 passing**; GitHub Actions workflow (.github/workflows/ci.yml) runs tests + docker build.
- **Frontend**: change-password dialog, Devices **pagination + search**, **config-backup viewer**, SNMPv3 fields, live socket updates.

## Remaining caveats (not gaps — need external systems to exercise)
- Email only fires with a real SMTP server configured; SNMPv3/health polling needs real devices; CI runs on GitHub (not in this environment).
