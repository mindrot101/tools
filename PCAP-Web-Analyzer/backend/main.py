"""PCAP Analyzer API — async jobs, auth, filters, diff, reports, live capture."""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import (Depends, FastAPI, File, Form, Header, HTTPException, Query,
                     Request, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

import auth
import chunked
import diff as diff_mod
import filters as filters_mod
import jobs as jobs_mod
import report as report_mod
import settings
import storage
from settings import get_logger

log = get_logger("pcap.api")
UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024
_MAGICS = (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x4d\x3c\xb2\xa1",
           b"\xa1\xb2\x3c\x4d", b"\x0a\x0d\x0d\x0a")

executor = ThreadPoolExecutor(max_workers=2)
_START = time.time()
_rate: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global executor
    executor = ThreadPoolExecutor(max_workers=2)
    storage.init_db()
    auth.ensure_admin()
    if settings.RETENTION_DAYS > 0:
        purged = storage.purge_older_than(time.time() - settings.RETENTION_DAYS * 86400)
        log.info("retention purge", extra={"extra_fields": {"purged": purged}})
    yield
    executor.shutdown(wait=False)


app = FastAPI(title="PCAP Analyzer API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------- helpers ----------
def _safe_name(name: str) -> str:
    import os, re
    base = os.path.basename(name or "capture.pcap")
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return base[:100] or "capture.pcap"


def _valid_ext(name: str) -> bool:
    return name.lower().endswith((".pcap", ".pcapng", ".cap"))


def rate_limit(request: Request):
    ip = request.client.host if request.client else "?"
    now = time.time()
    win, cnt = _rate.get(ip, (now, 0))
    if now - win >= 60:
        win, cnt = now, 0
    cnt += 1
    _rate[ip] = (win, cnt)
    if cnt > settings.RATE_LIMIT_PER_MIN:
        raise HTTPException(429, "Rate limit exceeded")


def _owner_filter(user: dict) -> Optional[str]:
    if not settings.AUTH_ENABLED or user.get("is_admin"):
        return None
    return user["id"]


def _owned_job(job_id: str, user: dict) -> dict:
    job = storage.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if settings.AUTH_ENABLED and not user.get("is_admin") and job["owner_id"] != user["id"]:
        raise HTTPException(403, "Not your job")
    return job


def _enqueue(job_id: str, paths: List[Path], dedup: str, window: float):
    iocs = storage.get_setting("iocs", "")
    args = (job_id, [str(p) for p in paths], dedup, window, iocs)
    if settings.REDIS_URL:
        from redis import Redis
        from rq import Queue
        Queue("pcap", connection=Redis.from_url(settings.REDIS_URL)).enqueue(
            "jobs.run_job", *args, job_timeout=1800)
    else:
        executor.submit(jobs_mod.run_job, *args)


# ---------- auth ----------
@app.get("/auth/config")
async def auth_config():
    return {"auth_enabled": settings.AUTH_ENABLED}


@app.post("/auth/login")
async def login(username: str = Form(...), password: str = Form(...)):
    if not settings.AUTH_ENABLED:
        return {"token": auth.make_token("public"), "username": "public", "is_admin": True}
    user = storage.get_user_by_name(username)
    if not user or not auth.verify_password(password, user["pw_hash"]):
        raise HTTPException(401, "Invalid credentials")
    return {"token": auth.make_token(user["id"]), "username": user["username"],
            "is_admin": bool(user["is_admin"])}


@app.get("/auth/me")
async def me(user: dict = Depends(auth.current_user)):
    return {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])}


# ---------- upload / capture ----------
@app.post("/upload", dependencies=[Depends(rate_limit)])
async def upload_files(files: List[UploadFile] = File(...),
                       dedup: str = Query("content", pattern="^(content|none)$"),
                       time_window: float = Query(0.0, ge=0.0),
                       user: dict = Depends(auth.current_user)):
    if not files:
        raise HTTPException(400, "No files provided")
    job_id = uuid.uuid4().hex[:12]
    saved, names = [], []
    for i, f in enumerate(files):
        safe = _safe_name(f.filename)
        if not _valid_ext(safe):
            raise HTTPException(400, f"Invalid file type: {f.filename}")
        dest = UPLOAD_DIR / f"{job_id}_{i}_{safe}"
        size = 0
        with open(dest, "wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    out.close(); dest.unlink(missing_ok=True)
                    raise HTTPException(413, f"{safe} exceeds {settings.MAX_UPLOAD_MB} MB limit")
                out.write(chunk)
        with open(dest, "rb") as fh:
            if fh.read(4) not in _MAGICS:
                dest.unlink(missing_ok=True)
                raise HTTPException(400, f"{safe} is not a valid pcap/pcapng file")
        saved.append(dest); names.append(safe)
    storage.create_job(job_id, names, dedup, time_window, owner_id=user["id"])
    _enqueue(job_id, saved, dedup, time_window)
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "queued", "files": names})


@app.post("/uploads/init")
async def upload_init(filename: str = Form(...), user: dict = Depends(auth.current_user)):
    if not _valid_ext(_safe_name(filename)):
        raise HTTPException(400, "Invalid file type")
    return {"upload_id": chunked.init_upload(_safe_name(filename))}


@app.post("/uploads/{upload_id}/chunk")
async def upload_chunk(upload_id: str, request: Request, user: dict = Depends(auth.current_user)):
    data = await request.body()
    try:
        received = chunked.append_chunk(upload_id, data)
    except FileNotFoundError:
        raise HTTPException(404, "Unknown upload_id")
    if received > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload exceeds size limit")
    return {"received": received}


@app.post("/uploads/{upload_id}/complete", dependencies=[Depends(rate_limit)])
async def upload_complete(upload_id: str, dedup: str = Query("content", pattern="^(content|none)$"),
                          user: dict = Depends(auth.current_user)):
    job_id = uuid.uuid4().hex[:12]
    dest = UPLOAD_DIR / f"{job_id}_0.pcap"
    try:
        meta = chunked.complete_upload(upload_id, dest)
    except (FileNotFoundError, OSError):
        raise HTTPException(404, "Unknown or incomplete upload")
    with open(dest, "rb") as fh:
        if fh.read(4) not in _MAGICS:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, "Not a valid pcap/pcapng file")
    name = _safe_name(meta["filename"])
    storage.create_job(job_id, [name], dedup, 0.0, owner_id=user["id"])
    _enqueue(job_id, [dest], dedup, 0.0)
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "queued", "files": [name]})


@app.post("/capture")
async def capture(interface: str = Form(""), max_packets: int = Form(1000),
                  max_seconds: int = Form(30), dedup: str = Form("content"),
                  user: dict = Depends(auth.current_user)):
    if not settings.ENABLE_LIVE_CAPTURE:
        raise HTTPException(403, "Live capture disabled (set ENABLE_LIVE_CAPTURE=true and grant CAP_NET_RAW)")
    job_id = uuid.uuid4().hex[:12]
    storage.create_job(job_id, [f"live:{interface or 'any'}"], dedup, 0.0,
                       owner_id=user["id"], source="capture")
    executor.submit(jobs_mod.run_capture, job_id, interface, max_packets, max_seconds,
                    dedup, storage.get_setting("iocs", ""))
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "queued"})


# ---------- jobs ----------
@app.get("/jobs")
async def list_jobs(limit: int = Query(50, ge=1, le=200), user: dict = Depends(auth.current_user)):
    return {"jobs": storage.list_jobs(limit, owner_id=_owner_filter(user))}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str, user: dict = Depends(auth.current_user)):
    return _owned_job(job_id, user)


@app.get("/jobs/{job_id}/packets")
async def get_packets(job_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                      proto: Optional[str] = None, include_dups: bool = True,
                      filter: str = "", user: dict = Depends(auth.current_user)):
    _owned_job(job_id, user)
    try:
        where, params = filters_mod.compile_filter(filter)
    except ValueError as e:
        raise HTTPException(400, f"Invalid filter: {e}")
    return {
        "total": storage.count_packets(job_id, include_dups, proto, where, params),
        "offset": offset, "limit": limit,
        "packets": storage.get_packets(job_id, offset, limit, proto, include_dups, where, params),
    }


@app.get("/jobs/{job_id}/download")
async def download(job_id: str, format: str = Query("json", pattern="^(json|csv)$"),
                   user: dict = Depends(auth.current_user)):
    job = _owned_job(job_id, user)
    if format == "json":
        return JSONResponse(job)
    return StreamingResponse(_csv_rows(job_id), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=pcap_{job_id}.csv"})


def _csv_rows(job_id):
    import csv, io
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["idx", "ts", "src", "dst", "proto", "sport", "dport", "length", "protocols", "is_dup"])
    yield buf.getvalue(); buf.seek(0); buf.truncate(0)
    off = 0
    while True:
        page = storage.get_packets(job_id, off, 1000)
        if not page:
            break
        for p in page:
            w.writerow([p["idx"], p["ts"], p["src"], p["dst"], p["proto"], p["sport"],
                        p["dport"], p["length"], "|".join(p["protocols"]), p["is_dup"]])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        off += 1000


@app.get("/jobs/{job_id}/report", response_class=HTMLResponse)
async def job_report(job_id: str, user: dict = Depends(auth.current_user)):
    return report_mod.html_report(_owned_job(job_id, user))


@app.post("/jobs/{job_id}/share")
async def share_job(job_id: str, user: dict = Depends(auth.current_user)):
    _owned_job(job_id, user)
    import secrets
    token = secrets.token_urlsafe(16)
    storage.update_job(job_id, share_token=token)
    return {"share_token": token}


@app.delete("/jobs/{job_id}/share")
async def unshare_job(job_id: str, user: dict = Depends(auth.current_user)):
    _owned_job(job_id, user)
    storage.update_job(job_id, share_token=None)
    return {"unshared": job_id}


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str, user: dict = Depends(auth.current_user)):
    _owned_job(job_id, user)
    storage.delete_job(job_id)
    return {"deleted": job_id}


# ---------- shared (public, no auth) ----------
@app.get("/shared/{token}")
async def shared_job(token: str):
    job = storage.get_job_by_share(token)
    if not job:
        raise HTTPException(404, "Not found")
    return job


@app.get("/shared/{token}/report", response_class=HTMLResponse)
async def shared_report(token: str):
    job = storage.get_job_by_share(token)
    if not job:
        raise HTTPException(404, "Not found")
    return report_mod.html_report(job)


# ---------- diff ----------
@app.get("/diff")
async def diff(a: str, b: str, user: dict = Depends(auth.current_user)):
    _owned_job(a, user); _owned_job(b, user)
    return diff_mod.compare(a, b)


# ---------- settings: IOCs ----------
@app.get("/settings/iocs")
async def get_iocs(user: dict = Depends(auth.current_user)):
    return {"iocs": storage.get_setting("iocs", "")}


@app.put("/settings/iocs")
async def put_iocs(body: dict, user: dict = Depends(auth.require_admin) if settings.AUTH_ENABLED else Depends(auth.current_user)):
    storage.set_setting("iocs", body.get("iocs", ""))
    return {"ok": True}


# ---------- saved filters ----------
@app.get("/filters")
async def get_filters(user: dict = Depends(auth.current_user)):
    return {"filters": storage.list_filters(user["id"])}


@app.post("/filters")
async def add_filter(body: dict, user: dict = Depends(auth.current_user)):
    expr = body.get("expression", "")
    try:
        filters_mod.compile_filter(expr)
    except ValueError as e:
        raise HTTPException(400, f"Invalid filter: {e}")
    fid = uuid.uuid4().hex[:10]
    storage.add_filter(fid, user["id"], body.get("name", "filter"), expr)
    return {"id": fid}


@app.delete("/filters/{fid}")
async def del_filter(fid: str, user: dict = Depends(auth.current_user)):
    storage.delete_filter(fid)
    return {"deleted": fid}


# ---------- ops ----------
@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    counts = storage.job_counts()
    lines = [f'pcap_uptime_seconds {round(time.time() - _START, 1)}']
    for status in ("queued", "processing", "done", "error"):
        lines.append(f'pcap_jobs{{status="{status}"}} {counts.get(status, 0)}')
    lines.append(f'pcap_auth_enabled {1 if settings.AUTH_ENABLED else 0}')
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
