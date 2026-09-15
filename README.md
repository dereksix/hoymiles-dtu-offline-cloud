# hoymiles-dtu-offline-cloud

Run your **OEM Hoymiles DTU‑Pro / DTU‑Pro‑S fully offline** — point it at your own
machine as its "S‑Miles cloud" and keep every byte on your LAN. Includes the
reverse‑engineered **DTU → cloud protocol**, a working **cloud emulator** (the DTU does
its full handshake against *you*), **command push over Ethernet** (reboot / inverter
start‑stop / power‑limit), plus **account‑free local commissioning** and a recipe to
**trap the DTU off the Hoymiles cloud** at your gateway.

> **Why this exists.** Two existing worlds: use Hoymiles' cloud (needs an installer
> account — a real blocker for DIY/US owners), or throw the OEM DTU away and run
> [OpenDTU](https://github.com/tbnobody/OpenDTU)/Ahoy on an ESP32. This is the missing
> middle: **keep the OEM DTU** (its RF binding, its grid‑compliance firmware, its
> Modbus) but cut the cloud and own it locally.

## Status — proof of concept

Tested against a **DTU‑Pro‑S** (wifi fw `2.3.0.0-de`, sw `527`) with **HMS‑800‑2T‑NA**
microinverters. Working and verified:

- ✅ DTU → cloud handshake fully decoded (register / time‑sync / APPInfo / heartbeat)
- ✅ Emulator the real OEM DTU accepts and stays "online" against — no Hoymiles, no internet
- ✅ **Command push over Ethernet** — pushed a reboot down the cloud socket; the DTU obeyed
- ✅ Account‑free commissioning message (`AutoSearch`) over the DTU's local AP
- ⚠️ **TODO:** decode the live `RealData` production frames (structure known, needs a
  DTU with bound inverters to capture); more DTU models/firmwares; a cleaner injector API.

PRs welcome — especially captures from other DTU models so we can generalise.

## How it relates to existing projects

- [`suaveolent/hoymiles-wifi`](https://github.com/suaveolent/hoymiles-wifi) — **app → DTU**
  local protobuf (read + power control over the DTU AP). This repo depends on it for the
  protobuf definitions and uses it for commissioning.
- [`henkwiedig/Hoymiles-DTU-Proto`](https://github.com/henkwiedig/Hoymiles-DTU-Proto) —
  DTU protobuf defs + capture parsing.
- **Novel here:** the **DTU → cloud** direction — frame format, CRC, the registration
  handshake, a cloud **emulator**, and **cloud→DTU command push**. See
  [`PROTOCOL.md`](PROTOCOL.md).

## The three pieces

### 1. Commission microinverters without an account (`commission.py`)
Join the DTU's own open Wi‑Fi AP `DTUP-<serialtail>` (gateway `10.10.100.254`), then:

```bash
pip install hoymiles-wifi
python commission.py --host 10.10.100.254 --local-addr <your-AP-ip> \
    --dtu-sn <DTU_SERIAL> --mi <MI_SERIAL_INT> --mi <MI_SERIAL_INT>
```
Microinverter serials are 12 hex digits on the sticker; pass them as ints
(`int("112100ABCDEF",16)`). The DTU auto‑binds them over its sub‑1 GHz radio (they must
be **powered by their panels** — ≥ startup DC — to answer).

### 2. Point the DTU at your machine + trap it off the cloud (`set_server.py`)
Over the same AP, redirect the DTU's server + DNS to your host:
```bash
python set_server.py --host 10.10.100.254 --local-addr <your-AP-ip> \
    --server <YOUR_HOST_IP> --dns <YOUR_HOST_IP> --restart
```
Then **block it at your gateway** so it can never reach Hoymiles regardless of its
hardcoded DNS (many ship a hardcoded public resolver):
- Firewall: drop/deny the DTU's IP (or MAC) to WAN — keep LAN so your host + Modbus work.
- Optional DNS: sinkhole `datana.hoymiles.com` → your host and blackhole
  `fwupdate.hoymiles.com` to kill OTA.

The DTU only *listens* for the rich protobuf on its Wi‑Fi AP, never on its Ethernet IP —
so "control over Ethernet" is done by making it **dial your emulator** (below), not by it
listening.

### 3. Be its cloud (`cloud_emu.py`)
```bash
python cloud_emu.py            # binds 0.0.0.0:10081
# or run it as a service — see hoymiles-cloud.service
```
The DTU connects, registers, and stays online against you. Push a command any time:
```bash
echo "1" > inject.cmd                       # 1 = reboot the DTU
echo "7" > inject.cmd                        # 7 = shut a microinverter down
echo "8|A:1000,B:0,C:0" > inject.cmd         # 8 = power-limit 100.0%
```
Action codes are the `CMD_ACTION_*` values in `hoymiles_wifi/const.py`. See
[`PROTOCOL.md`](PROTOCOL.md) for the frame format and the full handshake.

## Safety & legality

This talks to **hardware you own** for interoperability and local control — the same
category as OpenDTU. It does not touch anyone else's device or Hoymiles' servers (in fact
it's about *not* talking to them). Curtailment/shutdown commands affect grid‑tied
equipment: know your local rules and don't push commands you don't understand. No
warranty — see `LICENSE`.

## Credits
Protocol groundwork from `hoymiles-wifi` and `Hoymiles-DTU-Proto`. Cloud direction,
emulator, and command‑push reverse‑engineered by capturing one real DTU↔cloud session
and rebuilding the server side.
