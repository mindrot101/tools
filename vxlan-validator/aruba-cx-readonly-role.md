# AOS-CX Read-Only Service Account (switch-side enforcement)

This is **layer 3 of 3** in the validator's read-only design. Apply it on every
switch the tool will reach. Even if a bug slipped past the catalog contract
(layer 1) and the command guard (layer 2), the switch itself will refuse any
command outside this allowlist.

The three layers:

1. **Catalog contract** — every test declares `read_only=True` and only `show` /
   `ping` / `traceroute` CLI plus REST `GET`.
2. **Command guard** (`app/guard.py`) — parses every outgoing command, blocks any
   non-read-only verb, metacharacter, chaining, redirection, or substitution, and
   permits only `GET`/`HEAD`/`OPTIONS` on REST.
3. **AOS-CX role** (this file) — the service account on the switch is authorized
   for read commands only.

---

## Option A — Local command-authorization role (AOS-CX)

```
! Create a read-only role for the validator service account.
role vxlan-validator-ro
    10 rule permit command "show *"
    20 rule permit command "ping *"
    30 rule permit command "ping6 *"
    40 rule permit command "traceroute *"
    50 rule permit command "traceroute6 *"
    ! Everything not explicitly permitted is denied by default.

! Local service account bound to the read-only role.
user vxlan-svc group vxlan-validator-ro password plaintext <SET-A-STRONG-PASSWORD>
```

> Exact `role` rule syntax varies slightly by AOS-CX version. On platforms/firmware
> that do not support per-command local roles, use the TACACS+ option below, which
> is the more common enterprise posture anyway.

## Option B — TACACS+ command authorization (recommended for enterprise)

Bind the service account to a TACACS+ command set that permits only the verbs
above. On the switch, enable command authorization:

```
aaa authorization commands default group tacacs+
```

On the TACACS+ server (ISE / ClearPass / tac_plus), the `vxlan-svc` account's
command set should:

- **permit**: `show`, `ping`, `ping6`, `traceroute`, `traceroute6`
- **deny**: everything else (default deny), explicitly including
  `configure`, `write`, `copy`, `erase`, `reload`, `boot`, `no`, `clear`,
  `checkpoint`, `debug`, and shell access.

## REST access

The validator uses only `GET` against `/rest/v10.x/...`. Grant the service
account REST read access; do not grant write. On AOS-CX, REST honors the same
user role, so binding `vxlan-svc` to the read-only role covers REST as well.

## Management-plane hygiene

- Source all validator traffic from the **mgmt VRF**; scope the account and any
  ACLs accordingly.
- Respect the CX **concurrent session limit**; the validator caps sessions per
  switch (`VXV_MAX_SESSIONS`, default 2) but the switch-side limit is the backstop.
- Rotate the service-account password on your normal cadence.

## Verify

From the service account, confirm a write is refused:

```
switch# configure terminal
% Command authorization failed.        <-- expected
switch# show vxlan vteps               <-- permitted
```

Once verified, point a Connection profile in the validator at this account.
