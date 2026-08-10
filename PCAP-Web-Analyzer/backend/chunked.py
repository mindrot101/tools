"""Resumable/chunked upload assembly on the filesystem."""
import json
import os
import uuid
from pathlib import Path
from typing import Dict

import settings

CHUNK_DIR = Path(settings.DATA_DIR) / "chunks"


def init_upload(filename: str) -> str:
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex[:16]
    d = CHUNK_DIR / upload_id
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({"filename": filename, "received": 0}))
    (d / "data.part").write_bytes(b"")
    return upload_id


def append_chunk(upload_id: str, data: bytes) -> int:
    d = CHUNK_DIR / upload_id
    if not d.exists():
        raise FileNotFoundError("unknown upload_id")
    with open(d / "data.part", "ab") as f:
        f.write(data)
    meta = json.loads((d / "meta.json").read_text())
    meta["received"] += len(data)
    (d / "meta.json").write_text(json.dumps(meta))
    return meta["received"]


def complete_upload(upload_id: str, dest: Path) -> Dict:
    d = CHUNK_DIR / upload_id
    meta = json.loads((d / "meta.json").read_text())
    os.replace(d / "data.part", dest)
    for f in d.iterdir():
        f.unlink()
    d.rmdir()
    return {"filename": meta["filename"], "size": dest.stat().st_size}
