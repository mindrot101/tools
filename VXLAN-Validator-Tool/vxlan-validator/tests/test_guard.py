"""Safety-critical tests for the read-only command guard."""
from app.guard import vet_cli, vet_rest


ALLOWED = [
    "show interface vxlan1",
    "show running-config interface vxlan1",
    "show int vxlan vteps",
    "show vni",
    "show vsx status keepalive",
    "show interface vxlan1 counters",
    "show interface | include MTU",
    "show running-config | include access-list",
    "ping 10.255.0.21 vrf default source loopback 1 size 8972 df-bit repetitions 5",
    "traceroute 10.0.10.11 vrf default",
    "show access-lists hitcounts",
    "show mac-address-table vni 10100",
    "show capacities-status",
    "SHOW VSX STATUS",  # case-insensitive verb
]

BLOCKED = [
    "configure terminal",
    "conf t",
    "write memory",
    "copy running-config startup-config",
    "erase startup-config",
    "reload",
    "no interface vxlan1",
    "clear counters",
    "interface vxlan1",
    "vni 10100",
    "boot system primary",
    "debug vxlan",
    "start-shell",
    "bash",
    "show running-config ; erase startup-config",   # chaining via ;
    "show vni && reload",                            # chaining via &
    "show vni | reload",                             # pipe to non-filter
    "show run > flash:cfg.txt",                      # redirection
    "show vni `reload`",                             # backtick substitution
    "show vni $(reload)",                            # $() substitution
    "show vni\nconfigure terminal",                  # embedded newline
    "show interface | include x | configure",        # config in pipe
    "",                                              # empty
    "   ",                                           # whitespace only
]


def test_allowed_commands_pass():
    for cmd in ALLOWED:
        v = vet_cli(cmd)
        assert v.allowed, f"should have ALLOWED: {cmd!r} -> {v.reason}"


def test_blocked_commands_denied():
    for cmd in BLOCKED:
        v = vet_cli(cmd)
        assert not v.allowed, f"should have BLOCKED: {cmd!r}"


def test_rest_get_only():
    assert vet_rest("GET", "/rest/v10.13/system/vxlans").allowed
    assert vet_rest("HEAD", "/rest/v10.13/system").allowed
    for m in ("POST", "PUT", "PATCH", "DELETE"):
        assert not vet_rest(m, "/rest/v10.13/system/vxlans").allowed


if __name__ == "__main__":
    test_allowed_commands_pass()
    test_blocked_commands_denied()
    test_rest_get_only()
    print("guard tests passed")
