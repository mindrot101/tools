"""Central configuration + structured logging."""
import json
import logging
import os
import sys
import time


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


DATA_DIR = os.environ.get("DATA_DIR", "data")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploaded_pcaps")
EXTRACT_DIR = os.environ.get("EXTRACT_DIR", os.path.join(DATA_DIR, "extracted"))
MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", 512)
KEEP_RAW = env_bool("KEEP_RAW", False)
EXTRACT_FILES = env_bool("EXTRACT_FILES", False)

REDIS_URL = os.environ.get("REDIS_URL", "")
AUTH_ENABLED = env_bool("AUTH_ENABLED", False)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
TOKEN_TTL = env_int("TOKEN_TTL", 86400)

ENABLE_LIVE_CAPTURE = env_bool("ENABLE_LIVE_CAPTURE", False)
RETENTION_DAYS = env_int("RETENTION_DAYS", 0)          # 0 = keep forever
RATE_LIMIT_PER_MIN = env_int("RATE_LIMIT_PER_MIN", 120)

# detection thresholds
SCAN_PORT_THRESHOLD = env_int("SCAN_PORT_THRESHOLD", 50)
SCAN_HOST_THRESHOLD = env_int("SCAN_HOST_THRESHOLD", 25)
BEACON_MIN_HITS = env_int("BEACON_MIN_HITS", 6)
GEOIP_DB = os.environ.get("GEOIP_DB", "")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in getattr(record, "extra_fields", {}).items():
            payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def get_logger(name: str = "pcap") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(JsonFormatter())
        logger.addHandler(h)
        logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
        logger.propagate = False
    return logger
