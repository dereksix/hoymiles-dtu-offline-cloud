#!/usr/bin/env python3
"""Offline Hoymiles DTU cloud emulator.

Binds :10081 and answers the DTU's registration/time/APPInfo handshake with valid
CRC16/MODBUS frames, so a real OEM DTU-Pro(-S) stays "online" against this host with no
Hoymiles cloud and no internet. Also pushes commands DOWN the DTU's open socket: write a
line into the inject file (default ./inject.cmd) as "ACTION" or "ACTION|DATA".

See PROTOCOL.md. Point the DTU here first with set_server.py (and block it off the real
cloud at your gateway).

Env:
  EMU_BIND   bind address (default 0.0.0.0)
  EMU_PORT   bind port    (default 10081)
  EMU_LOG    log file      (default ./hoymiles-emu.log)
  EMU_INJECT inject file   (default ./inject.cmd)
  EMU_TZ_OFFSET  server-time offset hours (default 8, i.e. UTC+8 like S-Miles)
"""
import socket, threading, datetime, binascii, struct, time, os

BIND = os.environ.get("EMU_BIND", "0.0.0.0")
PORT = int(os.environ.get("EMU_PORT", "10081"))
LOG = os.environ.get("EMU_LOG", "./hoymiles-emu.log")
INJECT = os.environ.get("EMU_INJECT", "./inject.cmd")
TZ_OFFSET = int(os.environ.get("EMU_TZ_OFFSET", "8"))

active = {"sock": None}
sendlock = threading.Lock()


def log(m):
    line = f"{datetime.datetime.now().isoformat()} {m}"
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def crc16_modbus(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def vint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            break
    return out


def frame(cmd, seq, payload):
    return b"HM" + struct.pack(">HHHH", cmd, seq, crc16_modbus(payload), 10 + len(payload)) + payload


def server_time():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=TZ_OFFSET)).strftime(
        "%Y-%m-%d %H:%M:%S"
    ).encode()


def build_response(cmd, seq, payload):
    ep = int(time.time())
    ts = server_time()
    if cmd == 0x2202:  # register / time request -> time response
        p = b"\x08" + vint(99999) + b"\x10" + vint(ep) + b"\x1a" + bytes([len(ts)]) + ts
        return frame(0x2302, seq, p)
    if (cmd & 0xFF00) == 0x2200:  # any other DTU data upload -> generic ACK
        p = b"\x0a" + bytes([len(ts)]) + ts + b"\x10" + vint(99999) + b"\x28" + vint(ep)
        return frame(cmd + 0x0100, seq, p)
    return None


def build_command_payload(action, data):
    """CommandResDTO: 1=time, 2=action, 4=package_nub, 6=tid, 7=data(string)."""
    tid = int(time.time())
    p = b"\x08" + vint(tid) + b"\x10" + vint(action) + b"\x20" + vint(1) + b"\x30" + vint(tid)
    if data:
        db = data.encode()
        p += b"\x3a" + bytes([len(db)]) + db
    return p


def injector():
    seq = 0xF000
    while True:
        try:
            if os.path.exists(INJECT):
                spec = open(INJECT).read().strip()
                os.remove(INJECT)
                if spec:
                    parts = spec.split("|")
                    action = int(parts[0])
                    data = parts[1] if len(parts) > 1 else None
                    sock = active["sock"]
                    if sock:
                        seq = (seq + 1) & 0xFFFF
                        fr = frame(0x2305, seq, build_command_payload(action, data))
                        with sendlock:
                            sock.sendall(fr)
                        log(f"  >>> INJECT 0x2305 action={action} data={data} seq={seq}: {fr.hex()}")
                    else:
                        log(f"  >>> INJECT skipped: no DTU connected (action {action})")
        except Exception as e:  # noqa: BLE001
            log(f"injector err {e}")
        time.sleep(1)


def handle(c, a):
    active["sock"] = c
    log(f"DTU ONLINE {a}")
    c.settimeout(180)
    buf = b""
    try:
        while True:
            d = c.recv(4096)
            if not d:
                log(f"{a} closed")
                break
            buf += d
            while len(buf) >= 10 and buf[:2] == b"HM":
                total = struct.unpack(">H", buf[8:10])[0]
                if total < 10 or len(buf) < total:
                    break
                fr = buf[:total]
                buf = buf[total:]
                cmd = struct.unpack(">H", fr[2:4])[0]
                seq = struct.unpack(">H", fr[4:6])[0]
                pl = fr[10:]
                log(f"  RX cmd {cmd:04x} seq {seq} len {total}: {binascii.hexlify(pl).decode()}")
                r = build_response(cmd, seq, pl)
                if r:
                    with sendlock:
                        c.sendall(r)
                    log(f"  TX cmd {struct.unpack('>H', r[2:4])[0]:04x} seq {seq}")
    except Exception as e:  # noqa: BLE001
        log(f"{a} err {e}")
    finally:
        c.close()
        if active["sock"] is c:
            active["sock"] = None


def main():
    threading.Thread(target=injector, daemon=True).start()
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((BIND, PORT))
    s.listen(8)
    log(f"CLOUD EMULATOR up on {BIND}:{PORT} (offline; inject via {INJECT})")
    while True:
        c, a = s.accept()
        threading.Thread(target=handle, args=(c, a), daemon=True).start()


if __name__ == "__main__":
    main()
