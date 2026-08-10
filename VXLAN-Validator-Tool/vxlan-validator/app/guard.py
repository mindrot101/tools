"""
Read-only command guard.

This is the safety-critical core of the validator. Every CLI string and every
REST call bound for a switch passes through here first. The guard is an
ALLOWLIST, not a denylist: a command is permitted only if it clearly matches a
known read-only shape. Anything unrecognized is denied by default.

Enforcement layers (this file is layer 2 of 3):
  1. Test catalog     - every test declares read_only=True + allowed verbs
  2. Command guard    - THIS FILE - parses and vets every outgoing command
  3. AOS-CX role      - customer-applied switch-side role (see docs)

Nothing in this codebase constructs a config/write command. The guard exists so
that even a bug elsewhere cannot push a mutation to a customer device.
"""
from __future__ import annotations

from dataclasses import dataclass

# Verbs that begin a legitimate read-only operation on AOS-CX.
ALLOWED_CLI_VERBS: frozenset[str] = frozenset(
    {"show", "display", "ping", "ping6", "traceroute", "traceroute6"}
)

# Filter verbs permitted after a pipe in `show ... | <filter> <arg>`.
ALLOWED_PIPE_FILTERS: frozenset[str] = frozenset(
    {"include", "exclude", "begin", "count", "section", "grep"}
)

# Characters that enable command chaining, substitution, or redirection.
# Their presence anywhere in a command is an automatic denial.
FORBIDDEN_METACHARS: tuple[str, ...] = (
    ";", "&", "|&", "`", "$(", "$(", ">", "<<", "\n", "\r", "\\",
)

# Explicit mutating verbs. These can never appear as the leading token, but we
# also scan for them defensively so a crafted string like
# "show running-config ; erase startup-config" is caught by BOTH the metachar
# check and this list.
MUTATING_TOKENS: frozenset[str] = frozenset(
    {
        "configure", "conf", "config", "write", "copy", "erase", "delete",
        "remove", "rm", "boot", "reload", "reboot", "shutdown", "no",
        "clear", "checkpoint", "commit", "rollback", "debug", "diagnostic",
        "start-shell", "bash", "sh", "python", "install", "firmware",
        "update", "upgrade", "factory-default", "format", "mkdir",
        "set", "create", "enable", "disable", "insert", "replace", "move",
    }
)

ALLOWED_REST_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class GuardVerdict:
    allowed: bool
    command: str
    reason: str

    def as_dict(self) -> dict:
        return {"allowed": self.allowed, "command": self.command, "reason": self.reason}


def _tokens(command: str) -> list[str]:
    return command.strip().split()


def vet_cli(command: str) -> GuardVerdict:
    """Vet a single CLI command. Returns a verdict; never raises on bad input."""
    if command is None:
        return GuardVerdict(False, "", "empty command")

    raw = command.strip()
    if not raw:
        return GuardVerdict(False, "", "empty command")

    # 1. Reject shell/CLI metacharacters that enable chaining or redirection.
    #    We allow a single pipe '|' only for display filters, handled below,
    #    so '|' itself is not in FORBIDDEN_METACHARS but '|&' is.
    for mc in FORBIDDEN_METACHARS:
        if mc in raw:
            return GuardVerdict(False, raw, f"forbidden metacharacter {mc!r}")

    # 2. Split on the single allowed pipe. First segment is the command; any
    #    trailing segments must be display filters only.
    segments = raw.split("|")
    head = segments[0].strip()
    if not head:
        return GuardVerdict(False, raw, "empty command before pipe")

    head_tokens = _tokens(head)
    verb = head_tokens[0].lower()

    # 3. Leading verb must be on the read-only allowlist.
    if verb not in ALLOWED_CLI_VERBS:
        return GuardVerdict(False, raw, f"verb {verb!r} is not a read-only verb")

    # 4. Defensive scan: no mutating token anywhere in the head segment.
    for tok in head_tokens:
        if tok.lower() in MUTATING_TOKENS:
            return GuardVerdict(False, raw, f"mutating token {tok!r} present")

    # 5. Each pipe segment after the first must be an allowed display filter.
    for seg in segments[1:]:
        seg_tokens = _tokens(seg)
        if not seg_tokens:
            return GuardVerdict(False, raw, "empty pipe segment")
        fverb = seg_tokens[0].lower()
        if fverb not in ALLOWED_PIPE_FILTERS:
            return GuardVerdict(False, raw, f"pipe filter {fverb!r} not allowed")
        for tok in seg_tokens:
            if tok.lower() in MUTATING_TOKENS:
                return GuardVerdict(False, raw, f"mutating token {tok!r} in filter")

    return GuardVerdict(True, raw, "read-only")


def vet_rest(method: str, path: str) -> GuardVerdict:
    """Vet a single REST call. Only safe HTTP methods are permitted."""
    m = (method or "").strip().upper()
    label = f"{m} {path}"
    if m not in ALLOWED_REST_METHODS:
        return GuardVerdict(False, label, f"HTTP method {m!r} is not read-only")
    return GuardVerdict(True, label, "read-only")


def assert_cli(command: str) -> str:
    """Raise if the command is not read-only, else return it. For call sites
    that treat a guard failure as a hard programming error."""
    v = vet_cli(command)
    if not v.allowed:
        raise PermissionError(f"guard blocked CLI: {v.reason}: {command!r}")
    return v.command
