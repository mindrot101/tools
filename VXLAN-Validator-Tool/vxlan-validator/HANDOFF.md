# HANDOFF — VXLAN Validator for Aruba CX

One-page operator guide. Read-only fabric validation for **static (non-EVPN)**
VXLAN on Aruba CX. Ships as a single container with no external dependencies.

## What it is
- One image, one process. Serves the web UI and API on port **8080**.
- Runs out of the box in **simulated** mode (a seeded 4-VTEP / 6-VNI fabric with a
  deliberate MTU fault) so you can drive the whole workflow with no switches.
- Flip to **SSH** or **REST** to validate a live fabric. Strictly read-only.

## Prerequisites
- Docker + Docker Compose on a Linux host with reachability to the switch **mgmt
  VRF** (for live mode). Simulated mode needs no network at all.

## Run it (online host)
```bash
cp .env.example .env          # then edit VXV_API_KEY to a strong value
docker compose up -d --build
# open http://<host>:8080  and sign in with the API key from .env
```

## Run it (air-gapped site)
On a build host with internet:
```bash
docker compose build
docker save aruba-vxlan-validator:1.0 | gzip > vxlan-validator-1.0.tar.gz
```
Move the tarball + `docker-compose.yml` + `.env.example` to the target, then:
```bash
gunzip -c vxlan-validator-1.0.tar.gz | docker load
cp .env.example .env          # edit the API key
docker compose up -d          # 'build:' is skipped because the image already exists
```

## Get your API key
- If you set `VXV_API_KEY` in `.env`, that is your key.
- If you left it blank, one was generated on first boot:
  ```bash
  docker compose exec vxlan-validator cat /data/apikey.txt
  ```

## Sign in with a username/password
A built-in admin is created on first boot: **`admin` / `admin`** (use the
lower username/password fields on the login screen). This account is `admin`, so
it can manage Connection profiles. **Change the password before any non-lab use** —
set `VXV_ADMIN_PASS` in `.env` before first boot, or rotate it after signing in.

## Go live against real switches (read-only)
1. Apply the switch-side role to a service account on every switch —
   see **`aruba-cx-readonly-role.md`**.
2. In the UI: **Connections** → add a profile (host / mgmt IP, SSH or REST,
   the read-only service account, mgmt VRF).
3. **Test Runner** → set Executor to **SSH** (or REST), pick the profile,
   select tests + targets, **Run**.
4. Findings stream live; every run is saved under **History** and exportable
   from **Reports**.

## The read-only guarantee (three layers)
1. Catalog — only `show` / `ping` / `traceroute` + REST `GET` are ever declared.
2. Command guard — parses and blocks anything else before it leaves the container
   (chaining, redirection, substitution, and all write verbs are rejected).
3. AOS-CX role — the switch refuses non-read commands from the service account.

The header shows **🔒 Read-only — enforced** at all times. Blocked attempts (there
should be none in normal use) increment a counter and are written to the audit log
(`/data/audit.log` and container stdout).

## Ports, volumes, health
- Port **8080** (map elsewhere with `VXV_BIND`).
- Volumes: `/data` (SQLite DB, audit log, API key) and `/certs` (switch CA bundle).
- Liveness: `GET /api/health`. Container `HEALTHCHECK` is built in.

## Support notes
- Logs: `docker compose logs -f` (JSON audit lines are prefixed `AUDIT`).
- Reset state: `docker compose down && docker volume rm <project>_vxv-data`.
- Full deployment/security detail: **`deployment.md`**.
