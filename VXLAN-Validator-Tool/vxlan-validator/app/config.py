"""Runtime configuration, sourced entirely from environment variables."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # --- Server ---
    host: str = os.getenv("VXV_HOST", "0.0.0.0")
    port: int = int(os.getenv("VXV_PORT", "8080"))

    # --- Storage ---
    data_dir: str = os.getenv("VXV_DATA_DIR", "/data")
    db_path: str = ""

    # --- Auth ---
    # API key is the primary auth. If unset, one is generated at first boot and
    # written to <data_dir>/apikey.txt so the operator can retrieve it.
    api_key: str = os.getenv("VXV_API_KEY", "")
    # Signing secret for local-user session tokens.
    secret_key: str = os.getenv("VXV_SECRET_KEY", "")
    session_ttl_seconds: int = int(os.getenv("VXV_SESSION_TTL", "28800"))  # 8h
    local_users_enabled: bool = _bool("VXV_LOCAL_USERS", True)

    # --- Executor / device access ---
    # simulated | ssh | rest . Default simulated so the container runs with zero
    # external dependencies and never touches a real device until told to.
    default_executor: str = os.getenv("VXV_EXECUTOR", "simulated")
    # Load the demo fabric on first boot (simulated-mode convenience). Set false
    # to start empty and populate only from real discovery.
    seed_demo: bool = _bool("VXV_SEED_DEMO", True)
    # TLS verification for REST executor. verify=True by default; a lab-only
    # insecure override is audit-logged when used.
    ca_bundle: str = os.getenv("VXV_CA_BUNDLE", "/certs/ca-bundle.pem")
    ssh_timeout: int = int(os.getenv("VXV_SSH_TIMEOUT", "20"))
    rest_timeout: int = int(os.getenv("VXV_REST_TIMEOUT", "20"))
    max_sessions_per_switch: int = int(os.getenv("VXV_MAX_SESSIONS", "2"))

    version: str = "1.0.0"
    read_only: bool = True  # not configurable; this tool never writes.

    audit_path: str = field(default="")
    apikey_file: str = field(default="")

    def __post_init__(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        self.db_path = os.path.join(self.data_dir, "validator.db")
        self.audit_path = os.path.join(self.data_dir, "audit.log")
        self.apikey_file = os.path.join(self.data_dir, "apikey.txt")

        if not self.api_key:
            # Generate once and persist so restarts keep the same key.
            if os.path.exists(self.apikey_file):
                self.api_key = open(self.apikey_file).read().strip()
            else:
                self.api_key = "vxv_" + secrets.token_urlsafe(32)
                with open(self.apikey_file, "w") as fh:
                    fh.write(self.api_key + "\n")
                try:
                    os.chmod(self.apikey_file, 0o600)
                except OSError:
                    pass

        if not self.secret_key:
            self.secret_key = secrets.token_urlsafe(48)


settings = Settings()
