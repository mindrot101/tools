# Deployment & Security Guide

VXLAN Validator for Aruba CX — static (non-EVPN) fabric validation, read-only,
single container.

## 1. Architecture

One Python process (uvicorn) serves both the JSON API and the static UI. There is
no nginx, no supervisord, no external database, and no message broker — a
deliberate choice so the tool is air-gap friendly and trivial to hand to an ops
team.

```
┌──────────────────────────────────────────────┐
│  aruba-vxlan-validator:1.0  (python:3.12-slim)│
│                                                │
│  uvicorn :8080                                 │
│   ├── /                → static SPA (web/)     │
│   └── /api/*           → FastAPI               │
│         ├── read-only command guard  ★         │
│         ├── executors: simulated | ssh | rest  │
│         ├── discovery walker                   │
│         └── SQLite (/data/validator.db, WAL)   │
│                                                │
│  Volumes: /data (db, audit, apikey)            │
│           /certs (switch CA bundle, ro)        │
└──────────────────────────────────────────────┘
```

Executors are selected at run time. **simulated** (default) needs no network.
**ssh** uses Netmiko `send_command` only. **rest** uses httpx `GET` only. Both
device libraries are lazy-imported, so simulated deployments never load them.

## 2. Read-only enforcement (three layers)

1. **Catalog contract** — every `Test` declares `read_only=True` and only
   `show`/`ping`/`traceroute` CLI and REST `GET` endpoints.
2. **Command guard** (`app/guard.py`) — an allowlist. A command passes only if the
   leading verb is a known read-only verb; it is rejected on any forbidden
   metacharacter (`; & | & \` $() > << newline \\`), any mutating token, any pipe
   segment that is not a display filter, or any REST method other than
   `GET`/`HEAD`/`OPTIONS`. Blocks are audit-logged and counted.
3. **AOS-CX role** — the switch-side service account is authorized for read
   commands only. See `aruba-cx-readonly-role.md`.

The guard has a unit-test suite (`tests/test_guard.py`) covering chaining,
redirection, substitution, and embedded-newline attacks. Run it with
`PYTHONPATH=. python tests/test_guard.py`.

## 3. Configuration reference

All configuration is environment variables (see `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `VXV_BIND` | `8080` | Host port to publish (container listens on 8080). |
| `VXV_API_KEY` | *(generated)* | Primary auth key. If unset, generated to `/data/apikey.txt`. |
| `VXV_SECRET_KEY` | *(generated)* | Signs local-user session tokens. |
| `VXV_LOCAL_USERS` | `true` | Enable the secondary local-user auth path. |
| `VXV_ADMIN_USER` / `VXV_ADMIN_PASS` | — | Create an initial admin on first boot. |
| `VXV_EXECUTOR` | `simulated` | `simulated` \| `ssh` \| `rest`. |
| `VXV_CA_BUNDLE` | `/certs/ca-bundle.pem` | CA bundle for switch REST TLS verify. |
| `VXV_SSH_TIMEOUT` / `VXV_REST_TIMEOUT` | `20` | Per-call timeouts (seconds). |
| `VXV_MAX_SESSIONS` | `2` | Concurrent sessions per switch. |
| `VXV_DATA_DIR` | `/data` | SQLite, audit log, generated key. |

## 4. AuthN / AuthZ

- **API key** (primary) — sent as `X-API-Key`. Maps to the `operator` role.
- **Local users** (secondary) — bcrypt-hashed passwords in SQLite; login issues an
  HMAC-signed bearer token with a role and expiry. Roles: `viewer` < `operator` <
  `admin`.
- **Built-in default admin** — on first boot a default admin account
  (`admin` / `admin`) is created so the UI is usable with a username/password
  immediately. **Change this password before any non-lab deployment** — either set
  `VXV_ADMIN_PASS` before first boot, or sign in and rotate it. A hardcoded default
  credential is a finding in any security review; treat it as a lab convenience only.
- No anonymous access. `/api/health` and `/api/auth/login` are the only unauthenticated
  routes.
- Role gates: viewers read catalog/inventory/runs; operators run tests, discover, and
  import; admins manage connection profiles and read the full audit log.

## 5. Secrets & TLS

- Device credentials are stored server-side and **never returned to the browser**
  (the connections API does not select the secret column).
- For real deployments, prefer sourcing device creds from your secrets platform
  (Vault / CyberArk / cloud secret manager) and injecting them at profile-create
  time; the profile only needs to reference them.
- REST TLS verification uses the mounted CA bundle by default. A per-profile
  `insecure` override exists for labs and is **audit-logged** every time it is used.

## 6. Live-mode rollout (recommended sequence)

1. **Lab first.** Stand up the container, keep `VXV_EXECUTOR=simulated`, and walk
   the entire UI. Confirm the guard-block counter stays at 0.
2. **Apply the switch role** (`aruba-cx-readonly-role.md`) to a service account and
   verify a write is refused on the switch CLI.
3. **One profile, one pair.** Add a single Connection profile and run against one
   non-critical VTEP pair with the SSH executor.
4. **Confirm zero writes.** Review `/data/audit.log`: every `test.exec` entry should
   reference only `show`/`ping`/`traceroute`. There must be no config events.
5. **Expand** to the full fabric once a clean run is observed.
6. **Kill switch.** `docker compose stop vxlan-validator` halts all device access
   instantly.

## 7. Hardening for customer networks

- Put the container behind the customer's reverse proxy / TLS termination; do not
  expose 8080 publicly.
- Run on a host inside the mgmt network; source switch traffic from the mgmt VRF.
- Ship container logs to the customer SIEM (audit lines are JSON, prefixed `AUDIT`).
- Set a strong `VXV_API_KEY` and, if using local users, a strong initial admin.
- Retention: raw CLI output can contain MACs/IPs/tenant names. Rotate/prune the
  `/data` volume per the customer's data-handling policy.

## 8. Troubleshooting

| Symptom | Check |
|---|---|
| 401 on every call | API key mismatch — compare `.env` to `/data/apikey.txt`. |
| SSH executor `connect failed` | mgmt-VRF reachability, service-account creds, CX session limit. |
| REST test `error` / TLS failure | CA bundle path/contents, or set profile `insecure` for a lab. |
| MTU tests failing in simulated mode | expected — DC2-LEAF-02 is seeded at MTU 1500 to demo the flow. |
| Guard-block counter > 0 | inspect `/data/audit.log` `guard.block` entries; should never occur with the shipped catalog. |

## 9. What this tool is *not*

- Not EVPN. It validates **static** VXLAN (statically configured `vtep-peer` lists,
  HER flood lists). BGP-EVPN address families, Type-2/3/5 routes, and symmetric IRB
  are out of scope by design.
- Not a config tool. It will never write to a device.
