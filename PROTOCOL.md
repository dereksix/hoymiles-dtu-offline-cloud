# Hoymiles DTU ⇄ cloud protocol (reverse-engineered)

Covers the **DTU → cloud** (S-Miles server) direction, which the OEM DTU opens as an
outbound TCP connection to `datana.hoymiles.com:10081`. The **app → DTU** (local AP)
direction is already documented by
[`hoymiles-wifi`](https://github.com/suaveolent/hoymiles-wifi); the framing below is
identical, only the command codes differ (`0x23xx` cloud vs `0xa3xx` local AP).

Verified on a DTU-Pro-S (fw `2.3.0.0-de`). Serials shown as `<DTU_SN>` are your device's
12-char id.

## Frame format

```
+------+---------+---------+-----------+---------+------------------+
| "HM" | cmd (2) | seq (2) | CRC16 (2) | len (2) | protobuf payload |
+------+---------+---------+-----------+---------+------------------+
  0x484D  big-endian  big-endian  big-endian  big-endian = total frame length (incl. header)
```

- **CRC16** = CRC-16/MODBUS (poly `0x8005` reflected, init `0xFFFF`, no xor-out),
  computed over the **protobuf payload only** (not the header). In `crcmod`:
  `mkCrcFun(0x18005, rev=True, initCrc=0xFFFF, xorOut=0x0000)`.
- **seq** increments per request on the initiator; the responder **echoes** it.
- **Response command = request command + `0x0100`** (`0x2202 → 0x2302`, `0x2201 → 0x2301`).

## Handshake (DTU-initiated, on connect + then periodically)

The DTU holds the connection open and polls roughly every 30 s.

| Dir | cmd | meaning | payload (protobuf fields) |
|-----|------|---------|---------------------------|
| DTU→ | `0x2202` | register / time request | `1:99999`, `2:epoch`, `4:<DTU_SN>` |
| →DTU | `0x2302` | time response | `1:99999`, `2:epoch`, `3:"YYYY-MM-DD HH:MM:SS"` |
| DTU→ | `0x2201` | APPInfo upload | `1:<DTU_SN>`, `2:epoch`, …hw/sw/wifi ver (nested `8`) |
| →DTU | `0x2301` | ACK | `1:"YYYY-MM-DD HH:MM:SS"`, `2:99999`, `5:epoch` |
| DTU→ | `0x220b` | heartbeat / net-info | `1:<DTU_SN>`, `2:epoch`, nested status |
| →DTU | `0x230b` | ACK | same shape as `0x2301` |

The time string is in the **server timezone (UTC+8)**; the DTU applies its own offset.
A minimal responder that answers `0x2202` with a valid `0x2302` and ACKs the rest keeps
the DTU "online" indefinitely with no cloud.

## Command push (cloud → DTU)

The cloud pushes commands **down the connection the DTU opened**, unsolicited:

```
cmd = 0x2305   (CMD_CLOUD_COMMAND_RES_DTO)
payload = CommandResDTO {
    1: time (epoch)
    2: action        # CMD_ACTION_* from hoymiles_wifi/const.py
    4: package_nub = 1
    6: tid (epoch)
    7: data (string) # for parameterised actions, e.g. "A:1000,B:0,C:0" (power-limit 100.0%)
}
```

Common actions (`CMD_ACTION_*`):

| action | effect |
|--------|--------|
| 1  | DTU reboot |
| 3  | microinverter reboot |
| 6  | microinverter start |
| 7  | microinverter shutdown |
| 8  | limit power (`data` = `A:<pct*10>,B:0,C:0`) |
| 4  | collect versions |
| 50 | alarm list |

**Provisioning / commissioning** is `CommandResDTO` action **16 (`ID_NETWORKING`)**, NOT
AutoSearch. Payload: `dev_kind=1`, `package_nub=1`, `package_now=0` (omit the zero),
unique `tid`, `system_total_a=<count>`, and the serials as packed varints in
`mi_sn_item_a` (field 13) - a COMPLETE inventory replacement. The DTU restarts and
re-uploads its inventory. See `networking.py`.

> **Warning:** `AutoSearch` (`0xa313`) does NOT commission and returns a false
> `error_code: 0` because clients that don't match the response command/sequence will
> parse an unrelated cached APP-info frame as the expected reply. Always verify the
> response `cmd == request - 0x100` and the echoed `seq` before trusting a reply.

## Reproducing the capture

Point the DTU's `server_domain_name` at a logging TCP proxy that relays to the real
`datana.hoymiles.com:10081`, capture both directions, then cut. The four handshake
frames above are enough to build the emulator; capture a session from a **commissioned**
DTU to also get the `RealData` production upload frames (decode with
`hoymiles_wifi.protobuf.RealDataNew_pb2`).
