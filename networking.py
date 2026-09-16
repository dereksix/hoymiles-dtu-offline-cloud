"""DTU-Pro-S commissioning: ID_NETWORKING, not AutoSearch.
Default: read-only. --apply --replace-inventory replaces the COMPLETE inverter
list and can cause a DTU restart. No grid, power-limit or firmware changes.
Standard-library only. Verified on software 527 on 2026-09-16.
"""
import argparse, datetime, json, re, secrets, socket, struct, sys, time

def vi(n):
    if not 0 <= n < 1 << 64: raise ValueError('unsigned 64-bit value required')
    out = bytearray()
    while n > 127:
        out.append((n & 127) | 128); n >>= 7
    out.append(n)
    return bytes(out)

def field(n, v):
    if isinstance(v, int): return vi(n << 3) + vi(v)
    if isinstance(v, str): v = v.encode()
    return vi((n << 3) | 2) + vi(len(v)) + v

def decode(data):
    pos = 0; out = {}
    def readvi():
        nonlocal pos
        val = 0
        for shift in range(0, 70, 7):
            if pos >= len(data): raise ValueError('truncated varint')
            b = data[pos]; pos += 1; val |= (b & 127) << shift
            if not b & 128: return val
        raise ValueError('oversized varint')
    while pos < len(data):
        tag = readvi(); n, w = tag >> 3, tag & 7
        if not n: raise ValueError('zero field')
        if w == 0: v = readvi()
        elif w == 2:
            size = readvi(); v = data[pos:pos+size]; pos += size
            if pos > len(data): raise ValueError('truncated bytes')
        elif w in (1, 5):
            size = 8 if w == 1 else 4; v = data[pos:pos+size]; pos += size
        else: raise ValueError('unsupported wire type')
        out.setdefault(n, []).append(v)
    return out

def crc(data):
    c = 65535
    for b in data:
        c ^= b
        for _ in range(8): c = (c >> 1) ^ (0xA001 if c & 1 else 0)
    return c

def query(cmd, payload, seq=None, host='10.10.100.254', local_addr=None):
    if seq is None: seq = secrets.randbelow(65535)+1
    if cmd not in (0xa301, 0xa305): raise ValueError('command not permitted')
    if cmd == 0xa305:
        if decode(payload).get(2) != [16]: raise ValueError('Only ID_NETWORKING allowed')
    frame = b'HM' + struct.pack('>HHHH', cmd, seq, crc(payload), len(payload)+10) + payload
    with socket.socket() as s:
        s.settimeout(12)
        if local_addr: s.bind((local_addr, 0))
        s.connect((host,10081)); s.sendall(frame)
        data = b''; deadline = time.monotonic()+12
        while time.monotonic() < deadline:
            s.settimeout(max(0.1,deadline-time.monotonic()))
            while len(data) < 10:
                chunk = s.recv(4096)
                if not chunk: raise ValueError('short header')
                data += chunk
            total = struct.unpack('>H', data[8:10])[0]
            if not 10 <= total <= 65535: raise ValueError('invalid length')
            while len(data) < total:
                chunk = s.recv(4096)
                if not chunk: raise ValueError('short payload')
                data += chunk
            actual, rseq, check, _ = struct.unpack('>HHHH', data[2:10])
            payload = data[10:total]
            if data[:2] != b'HM' or check != crc(payload): raise ValueError('invalid frame/CRC')
            data = data[total:]
            print(json.dumps({'request':hex(cmd),'response':hex(actual),'sent_seq':seq,'received_seq':rseq,'bytes':total,'crc_ok':True}),flush=True)
            expected_seq = seq
            if actual == cmd-0x100 and rseq == expected_seq: return decode(payload)
        raise TimeoutError('no matching command response')

def printable(v):
    if isinstance(v, bytes):
        try: return v.decode('ascii') if all(32 <= b < 127 for b in v) else {'hex':v.hex()}
        except UnicodeDecodeError: return {'hex':v.hex()}
    if isinstance(v, list): return [printable(x) for x in v]
    if isinstance(v, dict): return {k:printable(x) for k,x in v.items()}
    return v


def serial(value):
    if re.fullmatch(r'[0-9a-fA-F]{12}', value): number=int(value,16)
    elif value.isdecimal() and len(value)>12: number=int(value)
    else: raise argparse.ArgumentTypeError('use 12-digit sticker hex or its decimal integer (>12 digits)')
    if not 0 < number < 1 << 48: raise argparse.ArgumentTypeError('serial must fit six nonzero bytes')
    return number

def networking_payload(serials, transaction):
    if not serials or len(serials)>99 or len(set(serials))!=len(serials):
        raise ValueError('supply 1..99 distinct serials; empty inventory prohibited')
    # CommandResDTO: package_nub=1; package_now=0 is the omitted default.
    # system_total_a=count, mi_sn_item_a=packed complete inverter inventory.
    return (field(1,transaction)+field(2,16)+field(3,1)+field(4,1)+field(6,transaction)
            +field(10,len(serials))+field(13,b''.join(vi(s) for s in serials)))

def inventory(host, local_addr):
    stamp=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    r=query(0xa301,field(1,stamp)+field(2,28800)+field(5,int(time.time())),
            host=host,local_addr=local_addr)
    devices=[]
    for raw in r.get(11,[]):
        inv=decode(raw); sn=inv.get(2,[0])[0]
        if sn: devices.append({'serial':f'{sn:012X}','firmware':inv.get(4,[0])[0]})
    return {'dtu_serial':r.get(1,[b''])[0].decode('ascii'),
            'device_count':r.get(3,[0])[0],'pv_count':r.get(4,[0])[0],'inverters':devices}

def validate_ack(ack, transaction, dtu_sn):
    if (ack.get(1,[b''])[0].decode('ascii')!=dtu_sn
            or ack.get(3)!=[16] or ack.get(6)!=[transaction]):
        raise ValueError('ACK identity/action/transaction mismatch')
    if ack.get(5,[0])[0]!=0: raise ValueError('DTU rejected networking command')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='10.10.100.254')
    p.add_argument('--local-addr')
    p.add_argument('--dtu-sn',help='optional expected DTU sticker serial')
    p.add_argument('--mi',action='append',type=serial,default=[])
    p.add_argument('--apply',action='store_true')
    p.add_argument('--replace-inventory',action='store_true',help='confirm the COMPLETE desired --mi list')
    p.add_argument('--wait',type=int,default=180,help='readback deadline, 0..300 seconds')
    a=p.parse_args()
    if not 0<=a.wait<=300: p.error('--wait must be 0..300')
    if a.apply and (not a.replace_inventory or not a.mi):
        p.error('--apply requires --replace-inventory and at least one --mi')
    before=inventory(a.host,a.local_addr); print(json.dumps({'before':before}),flush=True)
    if a.dtu_sn and a.dtu_sn.upper()!=before['dtu_serial']:
        raise ValueError('wrong DTU serial; nothing written')
    if not a.apply:
        print('Read-only: nothing written. Register with --apply --replace-inventory and the complete --mi list.')
        return 0
    transaction=int(time.time()); payload=networking_payload(a.mi,transaction)
    time.sleep(2)
    ack=query(0xa305,payload,host=a.host,local_addr=a.local_addr)
    validate_ack(ack,transaction,before['dtu_serial'])
    print('Networking acknowledged, NOT yet verified. DTU may restart; reconnect AP if needed.',flush=True)
    expected={f'{s:012X}' for s in a.mi}; deadline=time.monotonic()+a.wait
    while time.monotonic()<deadline:
        time.sleep(min(5,max(0,deadline-time.monotonic())))
        try:
            after=inventory(a.host,a.local_addr)
            if {v['serial'] for v in after['inverters']}==expected:
                print(json.dumps({'registered':after}),flush=True)
                print('Inventory verified. Firmware can be cached; verify fresh telemetry separately.')
                return 0
        except (OSError,ValueError): pass
    print('ACK received but registration NOT verified. Reconnect AP and rerun read-only; do not assume success.',file=sys.stderr)
    return 2

if __name__=='__main__':
    try: sys.exit(main())
    except (OSError,ValueError) as exc:
        print(f'FAILED: {exc}',file=sys.stderr); sys.exit(1)
