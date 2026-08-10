"""Job runner shared by the inline executor and the RQ worker."""
from pathlib import Path
from typing import List

import settings
import storage
from pcap_processor import process_files
from settings import get_logger

log = get_logger("pcap.jobs")


def run_job(job_id: str, paths: List[str], dedup: str, window: float, iocs_text: str = "") -> None:
    p_paths = [Path(p) for p in paths]
    try:
        storage.update_job(job_id, status="processing")

        def sink(rows):
            storage.add_packets(job_id, [(job_id, *r[1:]) for r in rows])

        def progress(n):
            storage.update_job(job_id, processed_packets=n)

        summary = process_files(p_paths, dedup=dedup, time_window=window,
                                sink=sink, progress=progress, iocs_text=iocs_text)
        storage.set_summary(job_id, summary)
        storage.update_job(job_id, status="done",
                           total_packets=summary["total_packets"],
                           unique_packets=summary["unique_packets"],
                           duplicates_removed=summary["duplicates_removed"])
        log.info("job done", extra={"extra_fields": {"job_id": job_id,
                 "packets": summary["total_packets"]}})
    except Exception as e:  # noqa: BLE001
        storage.update_job(job_id, status="error", error=f"{type(e).__name__}: {e}")
        log.error("job failed", extra={"extra_fields": {"job_id": job_id, "error": str(e)}})
    finally:
        if not settings.KEEP_RAW:
            for p in p_paths:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass


def run_capture(job_id: str, interface: str, max_packets: int, max_seconds: int,
                dedup: str, iocs_text: str = "") -> None:
    """Capture live traffic to a pcap, then run the normal analysis pipeline."""
    import capture
    out = Path(settings.UPLOAD_DIR) / f"{job_id}_capture.pcap"
    try:
        n = capture.capture_to_file(interface, out, max_packets, max_seconds)
        if n == 0:
            storage.update_job(job_id, status="error", error="No packets captured")
            out.unlink(missing_ok=True)
            return
        run_job(job_id, [str(out)], dedup, 0.0, iocs_text)
    except Exception as e:  # noqa: BLE001
        storage.update_job(job_id, status="error", error=f"{type(e).__name__}: {e}")
        out.unlink(missing_ok=True)
