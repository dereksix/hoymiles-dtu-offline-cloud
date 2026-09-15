#!/usr/bin/env python3
"""Commission Hoymiles microinverters into a DTU over its LOCAL AP (no cloud account).

Replicates what the installer app's auto-search does: sends an AutoSearch message with
the microinverter serials; the DTU then binds them over its sub-1GHz radio.

Prereq: join the DTU's open AP "DTUP-<serialtail>" (gateway 10.10.100.254), then:
    pip install hoymiles-wifi
    python commission.py --host 10.10.100.254 --local-addr <your AP ip> \
        --dtu-sn <DTU_SERIAL> --mi 18797000000001 --mi 18797000000002

Microinverter serials are the 12 hex digits on the sticker as an int: int("112100ABCDEF",16).
The inverters must be powered by their panels (>= startup DC) for the radio to answer.
"""
import argparse
import asyncio
import time

from hoymiles_wifi.dtu import DTU
from hoymiles_wifi.const import CMD_AUTO_SEARCH
from hoymiles_wifi.protobuf import AutoSearch_pb2


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="10.10.100.254")
    ap.add_argument("--local-addr", default=None, help="your IP on the DTU AP subnet")
    ap.add_argument("--dtu-sn", default=None, help="DTU serial; if omitted, read from the DTU")
    ap.add_argument("--mi", action="append", default=[], type=int,
                    help="microinverter serial as int (repeatable)")
    args = ap.parse_args()

    dtu = DTU(args.host, local_addr=args.local_addr)

    dtu_sn = args.dtu_sn
    if not dtu_sn:
        cfg = await dtu.async_get_config()
        if cfg is None:
            print("Could not read DTU config — are you joined to the DTU AP?")
            return
        dtu_sn = cfg.dtu_sn

    print(f"DTU {dtu_sn} -> AutoSearch with {len(args.mi)} MI serial(s): {args.mi}")
    req = AutoSearch_pb2.AutoSearchReqDTO()
    req.dtu_serial_number = dtu_sn
    req.time = int(time.time())
    req.package_number = 1
    req.current_package = 1
    for s in args.mi:
        req.mi_serial_numbers.append(s)

    res = await dtu.async_send_request(CMD_AUTO_SEARCH, req, AutoSearch_pb2.AutoSearchResDTO)
    if res is None:
        print("No immediate ACK (the DTU may have started an RF search). Verify with "
              "`python -m hoymiles_wifi --host <host> --local_addr <ip> identify-inverters`.")
    else:
        print("AutoSearchResDTO:", {"error_code": res.error_code, "time": res.time})


if __name__ == "__main__":
    asyncio.run(main())
