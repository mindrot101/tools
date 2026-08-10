# VXLAN Validator for Aruba CX

Read-only validation for **static (non-EVPN) VXLAN** implementations on Aruba CX
switches. Runs a catalog of tests across a discovered fabric — VTEP config,
tunnel state, MTU, head-end replication, data plane, VNI membership, MAC
learning, VSX, ARP, QoS, and hardware — and streams pass / warn / fail results
with per-test remediation.

**Strictly read-only.** The validator only issues `show` commands and REST `GET`
requests. It has no capability to write configuration to any device.

## Install (Docker)

```bash
git clone https://github.com/<your-username>/vxlan-validator.git
cd vxlan-validator
cp .env.example .env      # then edit .env — set VXV_ADMIN_USER / VXV_ADMIN_PASS
docker compose up -d --build
```

The app listens on port **8080** by default. Open `http://<host>:8080` and log
in with the admin credentials you set in `.env`.

**First-login checklist:**
1. Log in as the admin you defined in `.env`.
2. Delete the built-in `admin` account from the UI (see the security note below).
3. Confirm the executor mode — it defaults to `simulated` (demo data, no device
   access). Switch to `ssh` or `rest` in `.env` when you're ready to point it at
   real switches.

Change the exposed port by setting `VXV_BIND` in `.env` (e.g. `VXV_BIND=9090`).

> The `.env` file holds your secrets and is gitignored — it is never committed.
> `.env.example` is the committed template; copy it, don't edit it in place.

## Executors

| Mode | Value | Notes |
|------|-------|-------|
| Simulated | `simulated` (default) | Canned CLI seeded from demo inventory. No device access — safe for demos. |
| Live SSH | `ssh` | Real `show` commands over SSH (netmiko). |
| Live REST | `rest` | AOS-CX REST `GET` (httpx). |

Set the default with `VXV_EXECUTOR`. Live modes require a connection profile
(created in the UI by an admin) and, for REST, a CA bundle at
`/certs/ca-bundle.pem`.

## Configuration (environment variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `VXV_PORT` | `8080` | Container listen port |
| `VXV_BIND` | `8080` | Host port mapped in compose |
| `VXV_DATA_DIR` | `/data` | SQLite DB, audit log, API key file |
| `VXV_EXECUTOR` | `simulated` | `simulated` \| `ssh` \| `rest` |
| `VXV_LOCAL_USERS` | `true` | Enable local user auth (bcrypt) |
| `VXV_API_KEY` | auto | API key; auto-generated to `/data/apikey.txt` if unset |
| `VXV_SECRET_KEY` | auto | Session signing key; auto-generated if unset |
| `VXV_SESSION_TTL` | `28800` | Session lifetime (seconds) |
| `VXV_SEED_DEMO` | `true` | Load demo inventory on first boot |
| `VXV_ADMIN_USER` / `VXV_ADMIN_PASS` | — | Create an admin at first boot from env |
| `VXV_CA_BUNDLE` | `/certs/ca-bundle.pem` | CA bundle for REST TLS verification |
| `VXV_SSH_TIMEOUT` / `VXV_REST_TIMEOUT` | `20` | Per-connection timeouts (seconds) |
| `VXV_MAX_SESSIONS` | `2` | Max concurrent sessions per switch |

## Authentication

- **API key** — primary. Auto-generated on first boot and written to
  `/data/apikey.txt` (mode 0600) unless `VXV_API_KEY` is set.
- **Local users** — secondary, bcrypt-hashed. Roles: `viewer`, `operator`, `admin`.

### ⚠️ Change the default admin before any real use

On first boot, if no admin exists, the app creates a built-in admin with
username `admin` and password `admin` for ease of first access. **This is a
world-known credential — remove or replace it before pointing the validator at
any real network.**

Preferred: set `VXV_ADMIN_USER` and `VXV_ADMIN_PASS` in `.env` so a proper admin
is created at first boot and the `admin/admin` default is never the only account.
Then delete the default `admin` user from the UI.

## Data & persistence

State lives in the `vxv-data` volume (`/data`): SQLite DB (`validator.db`),
append-only audit log (`audit.log`), and the API key file. Mount `./certs`
read-only for REST CA trust.

## Aruba CX platform notes

- Validated against Aruba CX 8325 running GL.10.13.x.
- `show vni` is **not** a valid command on 8325 / GL.10.13.x. VNI, VLAN, and
  peer data are read from `show interface vxlan1` and
  `show running-config interface vxlan1`.
- Stay generic across CX platforms; platform-specific handling is applied only
  where a series requires it.

## Version

1.0.0 — read-only, static/non-EVPN scope.
