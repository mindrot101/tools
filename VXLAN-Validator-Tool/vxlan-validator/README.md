# VXLAN Validator for Aruba CX

**Version 1.1.0** · image tag `aruba-vxlan-validator:1.1` · see the [Changelog](#changelog)
and [Updating an existing deployment](#updating-an-existing-deployment).

A self-contained, **read-only** validation tool for **static (non-EVPN) VXLAN**
fabrics on Aruba CX switches. It walks the full stack — physical, L2/STP,
underlay routing, **MTU (including mismatch detection)**, L4, VTEP config, tunnel
state, VNI membership, MAC learning, head-end replication, data plane, QoS,
hardware tables, ARP, and VSX — running **49 checks across 15 categories** and
rolling the results into a per-layer health verdict. It **never writes to a
device**.

The whole application ships as a **single Docker container** with no external
database, no message broker, and no build-time Node dependency at runtime. It
runs out of the box in a seeded **simulated** mode (so you can learn the UI with
zero switches) and flips to real **SSH/REST** validation against a live fabric
with one setting.

> ⚠️ **Default credentials — change these immediately.**
> The app ships with a built-in admin account **`admin` / `admin`** so you can log
> in on first boot. **This is a convenience for evaluation only.** Before using
> this on any real or shared network, sign in, open **Users**, create your own
> admin account, and delete the default `admin` account — or remove the hardcoded
> block in `app/main.py` (see *Removing the default admin* below). A demo API key
> also ships in `.env.example`; change `VXV_API_KEY` before real use.

---

## What it does

Static VXLAN has no control plane to lean on — peers, VNIs, and flood lists are
configured by hand, so problems tend to be silent: a single low-MTU uplink that
black-holes jumbo tenant traffic, a VNI shut on one leaf, a VSX pair that isn't
really in sync, a peer missing from a static list. This tool systematically
checks each layer that contributes to overlay health and tells you **where** an
issue is, not just that something is wrong.

Key ideas:

- **Read-only by design, enforced in three independent layers** (see below). The
  tool is safe to point at a production customer fabric because it cannot issue
  anything but `show` / `ping` / `traceroute` and REST `GET`.
- **Full-stack coverage.** Because static VXLAN rides L2 and an IP underlay, the
  catalog deliberately includes physical errors, STP stability, underlay routing
  and MTU, and VSX — not just the VXLAN interface itself. Any layer can break the
  overlay, so any layer can raise a finding.
- **MTU focus.** A dedicated group hunts MTU mismatches end-to-end (per-hop,
  per-tunnel, per-VNI, DF-bit jumbo sweeps) because that's the most common and
  most silent static-VXLAN failure.
- **Discovery.** Point it at a seed switch and it walks the fabric from the
  static `vtep-peer` lists, dedupes VSX pairs, and builds the inventory for you.
- **Layer-health rollup.** Every run produces a HEALTHY / DEGRADED / CRITICAL
  verdict with a per-category breakdown, so an issue anywhere surfaces instead of
  getting lost in a 200-line result list.

## Tested against

The output parsers and check evaluators were developed and unit-tested against
**real output from an Aruba CX 8325 running AOS-CX `GL.10.13.1040`**
(`tests/fixtures/CORE_8325.txt`). Agent discovery and the parser-backed checks
match how that platform actually responds.

> **Platform note:** on this platform/firmware, `show vni` is **not** a valid
> command. VNI / VLAN / peer state is read from `show interface vxlan1` and
> `show running-config interface vxlan1`. The catalog and discovery use those.

Other CX platforms/firmware are expected to work but have not yet been validated
end-to-end; capturing real output from additional models is the way the check
parsers are hardened (see *Extending the parsers*).

## Read-only enforcement (three layers)

1. **Catalog contract** — every check only ever declares `show` / `ping` /
   `traceroute` CLI and REST `GET` endpoints.
2. **Command guard** (`app/guard.py`) — an allowlist that parses every outgoing
   command and blocks any write verb, shell metacharacter, command chaining,
   redirection, substitution, or non-GET REST method. Covered by an attack-case
   unit-test suite.
3. **AOS-CX role** (`aruba-cx-readonly-role.md`) — the switch service account is
   authorized for read commands only, so even a bug can't push a change.

The **🔒 Read-only — enforced** badge is always visible in the UI, and any blocked
attempt is counted and written to the append-only audit log.

---

## Prerequisites

- A Linux host (or VM) with **Docker Engine 20.10+** and the **Docker Compose
  plugin** (`docker compose`, v2). That's the only hard requirement.
- ~200 MB of disk for the image, a couple hundred MB of RAM.
- **For live validation only:** network reachability from the host to your
  switches' management interface (mgmt VRF), typically **TCP/22** for SSH and/or
  **TCP/443** for the AOS-CX REST API, plus a switch service account (ideally
  read-only — see `aruba-cx-readonly-role.md`).
- No internet access is required at runtime. Simulated mode needs no network at
  all. (Internet is only needed on the build host to pull base images/packages,
  or use the air-gapped `docker save` flow below.)

## Install with Docker

### Standard (host with internet)

```bash
git clone https://github.com/<your-username>/vxlan-validator.git
cd vxlan-validator

cp .env.example .env            # then edit VXV_API_KEY (and see the security notes)
docker compose up -d --build
```

Open **http://<host>:8080** and sign in (see *First login*).

### Air-gapped site

On a build host with internet:

```bash
docker compose build
docker save aruba-vxlan-validator:1.1 | gzip > vxlan-validator-1.1.tar.gz
```

Copy `vxlan-validator-1.1.tar.gz`, `docker-compose.yml`, and `.env.example` to the
target, then:

```bash
gunzip -c vxlan-validator-1.1.tar.gz | docker load
cp .env.example .env            # edit VXV_API_KEY
docker compose up -d            # image already loaded; build step is skipped
```

### Verify it's up

```bash
docker compose ps                       # STATUS should show (healthy)
curl -s localhost:8080/api/health       # {"status":"ok",...}
```

## Updating an existing deployment

Upgrading an already-running container (e.g. **1.0 → 1.1**) keeps your data: the
SQLite DB, audit log, and generated API key all live in the named `vxv-data`
volume, and `/certs` is a host bind-mount — neither is touched by a rebuild.

**No schema migration is required for the 1.1 release** — it's a
command-correction fix (see the [Changelog](#changelog)). The steps below are the
standard upgrade flow for any future version as well.

### Standard (host with internet)

From the repo directory on the deployed host:

```bash
cd vxlan-validator
git pull                                # pull the updated source (or copy the new files over)

docker compose build                    # rebuild the image (now tagged :1.1)
docker compose up -d                    # recreate the container from the new image
```

`docker compose up -d` recreates the `vxlan-validator` container only because the
image changed; the `vxv-data` volume is reattached as-is, so users, connection
profiles, history, and the API key all carry over.

Confirm the new version is live:

```bash
docker compose ps                       # STATUS → (healthy)
curl -s localhost:8080/api/health       # {"status":"ok","version":"1.1.0",...}
```

The `version` field in `/api/health` (and the footer in the UI) should now read
**1.1.0**. Old result/report history is preserved and remains readable.

### Air-gapped site

On the internet-connected build host, build and export the new image:

```bash
docker compose build
docker save aruba-vxlan-validator:1.1 | gzip > vxlan-validator-1.1.tar.gz
```

Copy `vxlan-validator-1.1.tar.gz` and the updated `docker-compose.yml` to the
target host, then load and recreate:

```bash
gunzip -c vxlan-validator-1.1.tar.gz | docker load     # loads aruba-vxlan-validator:1.1
docker compose up -d                                    # recreate from the loaded image
```

Because `docker-compose.yml` now pins `image: aruba-vxlan-validator:1.1`, Compose
recreates the container against the freshly loaded image while reusing the
`vxv-data` volume.

### Rollback

The previous image is still present locally after an upgrade. To revert, point the
`image:` tag in `docker-compose.yml` back to `aruba-vxlan-validator:1.0` and run
`docker compose up -d`. The data volume is compatible in both directions for the
1.0 ↔ 1.1 change (no schema change).

> **Tip:** back up the data volume before any upgrade you're unsure about:
> `docker run --rm -v vxv-data:/data -v "$PWD":/backup alpine tar czf /backup/vxv-data-backup.tgz -C /data .`

## First login

Two ways in:

- **API key (operator role):** whatever you set `VXV_API_KEY` to in `.env`
  (the shipped example is `vxv_demo_key_1234567890` — change it). If you leave it
  blank, a key is generated on first boot at `/data/apikey.txt`
  (`docker compose exec vxlan-validator cat /data/apikey.txt`).
- **Username / password (admin role):** the built-in **`admin` / `admin`**. Use
  the lower fields on the login screen. **Change this immediately** (see below).

Admins can manage users and connection profiles; operators can run tests and
discover; viewers can read reports.

## Usage workflow

1. **Connections** (admin) — add a device profile: name, switch mgmt IP, SSH or
   REST, and service-account credentials. Credentials are stored server-side and
   never returned to the browser.
2. **Discover** — pick a seed switch, the **Agent (SSH/REST)** adapter, and your
   profile. It logs in read-only, parses the vxlan1 config / VSX / loopback, walks
   the fabric, and lets you import what it finds.
3. **Topology** — review imported VTEPs, tunnels, VNIs, VSX pairs. Use **Clear all
   inventory** to drop the demo fabric before importing real gear.
4. **Test Runner** — select tests and targets, choose the executor
   (Simulated / SSH / REST), and Run. Results stream live.
5. **Reports / History** — every run is saved; Reports show the per-layer health
   rollup and export to JSON or print.

There's also an in-app **Guide** page that walks through all of this.

## Configuration

All configuration is environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `VXV_BIND` | `8080` | Host port to publish (container listens on 8080). |
| `VXV_API_KEY` | *(generated)* | Primary auth key. If unset, generated to `/data/apikey.txt`. |
| `VXV_SECRET_KEY` | *(generated)* | Signs local-user session tokens. |
| `VXV_LOCAL_USERS` | `true` | Enable username/password auth. |
| `VXV_EXECUTOR` | `simulated` | `simulated` \| `ssh` \| `rest`. |
| `VXV_SEED_DEMO` | `true` | Load the demo fabric on first boot. Set `false` to start empty. |
| `VXV_CA_BUNDLE` | `/certs/ca-bundle.pem` | CA bundle for switch REST TLS verify. |
| `VXV_SSH_TIMEOUT` / `VXV_REST_TIMEOUT` | `20` | Per-call timeouts (seconds). |
| `VXV_MAX_SESSIONS` | `2` | Concurrent sessions per switch. |
| `VXV_DATA_DIR` | `/data` | SQLite DB, audit log, generated key. |

Volumes: `/data` (SQLite, audit log, API key) and `/certs` (switch CA bundle).

## Removing the default admin

For a hardened deployment, do **one** of the following:

- **In-app (recommended):** sign in as `admin`, open **Users**, create your own
  admin account, then delete the `admin` account. (The app won't let you delete
  the last remaining admin, so create yours first.)
- **In code:** delete the built-in-admin block in `app/main.py` (the
  `auth.create_user("admin", "admin", "admin")` section) and rebuild. With
  `VXV_LOCAL_USERS=true` you can instead bootstrap a named admin on first boot via
  `VXV_ADMIN_USER` / `VXV_ADMIN_PASS`.

## Running the tests

```bash
pip install -r requirements.txt
PYTHONPATH=. python tests/test_guard.py       # read-only guard allowlist / attack cases
PYTHONPATH=. python tests/test_parsers.py     # parsers vs real 8325 output
PYTHONPATH=. python tests/test_discovery.py   # agent fabric-walk assembly
PYTHONPATH=. python tests/test_checks.py      # deterministic check verdicts
```

## Extending the parsers

The parser-backed checks (`app/checks.py`, `app/parsers.py`) are deterministic
where there's real ground-truth output. To harden a check for your platform,
capture the relevant `show` command output from a leaf and add it as a fixture —
the existing `tests/fixtures/CORE_8325.txt` is the model.

## Project layout

```
app/
  main.py            FastAPI app: API routes + static UI
  guard.py           read-only command guard  ★ safety core
  catalog.py         49-check catalog
  parsers.py         deterministic AOS-CX output parsers
  checks.py          parser-backed check evaluators
  runner.py          run engine (streaming NDJSON + layer-health rollup)
  auth.py            API key + local users (bcrypt) + RBAC
  db.py  audit.py  config.py  seed.py
  executors/         simulated | ssh (Netmiko) | rest (httpx GET-only)
  discovery/         seed-walk discovery (simulated + real agent)
web/                 buildless SPA (no Node at runtime)
tests/               guard, parser, discovery, and check suites + real fixture
Dockerfile  docker-compose.yml  .env.example
deployment.md  HANDOFF.md  aruba-cx-readonly-role.md
```

## Scope

**Static VXLAN only.** EVPN (BGP-EVPN address families, Type-2/3/5 routes,
symmetric IRB) is intentionally out of scope. The tool never writes to a device.

## Changelog

### 1.1.0

- **Fix: corrected the VTEP/tunnel state command.** The `tun-peers` and `tun-up`
  checks issued `show vxlan vteps`, which AOS-CX rejects with
  `Invalid input: vxlan`. On this platform the command is **`show int vxlan
  vteps`**. The wrong command caused those checks (and anything downstream reading
  tunnel/VNI/active-gateway state from that output) to report uniform false
  failures. The catalog now issues `show int vxlan vteps`; the read-only guard
  allowlist test and `aruba-cx-readonly-role.md` example were updated to match.
- No database schema change; upgrading from 1.0 preserves all data (see
  [Updating an existing deployment](#updating-an-existing-deployment)).

### 1.0.0

- Initial release: 49 read-only checks across 15 categories, three-layer
  read-only enforcement, simulated / SSH / REST executors, seed-walk discovery,
  single-container deployment.

## License

MIT — see `LICENSE`.
