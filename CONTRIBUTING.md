# Contributing

Thanks for helping! This started as a proof of concept on one DTU model, and the most
useful thing you can contribute is **data from other hardware**.

## Most wanted: captures from other DTU models / firmwares

The DTU→cloud handshake and the command frames are confirmed on a **DTU‑Pro‑S**
(`fw 2.3.0.0-de`). We need to know whether other DTUs (DTU‑Pro, DTU‑W100, DTU‑Lite,
different firmware) use the same framing, command codes, and CRC.

**How to capture a session** (non‑destructive, ~2 minutes):

1. Join the DTU's AP and point it at a host you control:
   `python set_server.py --host 10.10.100.254 --local-addr <ip> --server <YOUR_IP> --dns <YOUR_IP> --restart`
2. On `<YOUR_IP>`, run a logging TCP proxy on `:10081` that relays to the real
   `datana.hoymiles.com:10081` and prints both directions in hex. (A ~30‑line
   `socket` proxy — see the "Reproducing the capture" note in [PROTOCOL.md](PROTOCOL.md).)
3. Let it run through a full handshake, then **cut it back** (revert `set_server.py` to
   `--server datana.hoymiles.com --dns 223.5.5.5`, or just point it back at
   `cloud_emu.py`).
4. Open an issue with: DTU model + firmware, and the hex of both directions. **Redact
   your DTU/MI serials** (the 12‑char ids) if you'd rather not share them.

A capture from a **commissioned** DTU is especially valuable — it contains the live
`RealData` production frames we haven't decoded yet.

## Code

- `cloud_emu.py` stays **dependency‑free** (stdlib only) so it drops onto any Pi/box.
- The AP tools may use [`hoymiles-wifi`](https://github.com/suaveolent/hoymiles-wifi) for
  the protobuf definitions.
- Keep it readable; small focused PRs.

## Scope & safety

This is for controlling **your own** hardware locally. Please don't add anything that
targets devices you don't own or that phones home. Curtailment/shutdown commands touch
grid‑tied equipment — document them clearly.
