# PCAP Analyzer Web Application

Docker-hosted web app for uploading Wireshark captures (PCAP/PCAPNG), performing
**content-based deduplication**, deep protocol analysis, and **threat detection**.

## Features

- **Multi-file & resumable (chunked) upload** with size limit, filename sanitization, magic-byte validation.
- **Correct deduplication** — hashes full packet content (optional time window); flows are preserved.
- **Protocol analysis**: DNS, HTTP (with **TCP reassembly**, gzip/chunked decode, object extraction),
  TLS (version, **SNI**, **JA3 fingerprint**), ICMP, ARP, DHCP.
- **Threat detection**: IOC matching (IP/CIDR/domain), port-scan & beaconing heuristics,
  TCP expert-info (resets, retransmissions, zero-window), optional **GeoIP** enrichment.
- **Analytics**: protocol distribution, top talkers, conversations, DNS queries, TLS servers, JA3.
- **Async processing** via **Redis + RQ workers** (scales out); SQLite persistence + history.
- **Display filters** (mini query language) + saved queries; **paginated** packet browser.
- **PCAP diff** (compare two captures by content), **HTML reports**, **shareable public links**.
- **Live capture** from an interface (gated by `ENABLE_LIVE_CAPTURE` + `CAP_NET_RAW`).
- **Optional auth** (multi-user, per-job ownership, admin), **rate limiting**, **/metrics**,
  structured JSON logging, Docker healthcheck, retention/auto-purge.

## Ports (as deployed on Linux-Test)

| Service  | URL                          | Notes                                   |
|----------|------------------------------|-----------------------------------------|
| Frontend | http://<host>:8080           | remapped from 3000 (in use)             |
| Backend  | http://<host>:8081 (`/docs`) | remapped from 8000 (in use)             |
| Redis    | internal only                | no host port (isolated from other Redis)|
| Worker   | —                            | RQ worker, no host port                 |

## Quick start

```bash
docker compose -p pcap-web-analyzer up -d --build
```

## Key API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/upload` · `/uploads/init`·`/{id}/chunk`·`/{id}/complete` | Upload (direct or resumable) |
| POST | `/capture` | Start a live capture (if enabled) |
| GET  | `/jobs`, `/jobs/{id}` | History and job status + summary |
| GET  | `/jobs/{id}/packets?filter=&proto=&offset=&limit=` | Paginated packets w/ display filter |
| GET  | `/jobs/{id}/download?format=json\|csv`, `/jobs/{id}/report` | Exports and HTML report |
| POST/DELETE | `/jobs/{id}/share` | Create/revoke public share token |
| GET  | `/shared/{token}`, `/shared/{token}/report` | Public read-only access |
| GET  | `/diff?a=&b=` | Compare two captures |
| GET/PUT | `/settings/iocs` | Threat-intel indicators |
| GET/POST/DELETE | `/filters` | Saved display filters |
| POST | `/auth/login`, GET `/auth/me`, `/auth/config` | Auth (when enabled) |
| GET  | `/health`, `/metrics` | Ops |

## Configuration (backend env)

| Var | Default | Meaning |
|-----|---------|---------|
| `MAX_UPLOAD_MB` | `512` | Per-file upload cap |
| `KEEP_RAW` / `EXTRACT_FILES` | `false` | Keep raw pcaps / save extracted HTTP objects |
| `REDIS_URL` | (set in compose) | Enables RQ workers; unset = inline processing |
| `AUTH_ENABLED` / `ADMIN_USER` / `ADMIN_PASSWORD` / `SECRET_KEY` | off | Multi-user auth |
| `ENABLE_LIVE_CAPTURE` | `false` | Live capture (needs `CAP_NET_RAW`) |
| `GEOIP_DB` | — | Path to a GeoLite2 mmdb for enrichment |
| `RETENTION_DAYS` / `RATE_LIMIT_PER_MIN` | `0` / `120` | Auto-purge / rate limit |
| `SCAN_PORT_THRESHOLD` / `SCAN_HOST_THRESHOLD` / `BEACON_MIN_HITS` | `50/25/6` | Detection tuning |

## Enabling GeoIP enrichment

GeoIP/ASN enrichment (country/city for top talkers) ships enabled in the compose
config but needs a MaxMind-format `.mmdb` database, which is **not** included in
this repo (it is large, licensed, and refreshed monthly). Without it the app runs
normally and simply skips geolocation.

To turn it on:

1. **Obtain a database** (either works):
   - **DB-IP City Lite** — free, no signup:
     ```bash
     curl -L "https://download.db-ip.com/free/dbip-city-lite-$(date +%Y-%m).mmdb.gz" | gunzip > data/GeoLite2-City.mmdb
     ```
   - **MaxMind GeoLite2-City** — free with a MaxMind account/license key; download
     `GeoLite2-City.mmdb` and place it at `data/GeoLite2-City.mmdb`.

2. The compose file already sets `GEOIP_DB=/app/data/GeoLite2-City.mmdb` and mounts
   `./data` into the backend and worker, so the file is picked up automatically.
   (To use a different path, set the `GEOIP_DB` env var to match.)

3. **Restart** so the workers load the database:
   ```bash
   docker compose -p pcap-web-analyzer restart backend worker
   ```

Verify it is active:
```bash
docker exec pcap-web-worker python -c "import geoip; print(geoip.available(), geoip.lookup('8.8.8.8'))"
# -> True {'country': 'US', 'city': 'Mountain View'}
```

The database is a point-in-time snapshot; refresh it periodically (e.g. monthly)
by re-running step 1 and restarting.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest   # 14 tests
```
