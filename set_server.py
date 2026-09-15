#!/usr/bin/env python3
"""Point a Hoymiles DTU at your own server + DNS over its LOCAL AP (reversible).

Join the DTU AP "DTUP-<serialtail>" first, then:
  python set_server.py --host 10.10.100.254 --local-addr <AP ip> \
      --server <YOUR_HOST_IP> --dns <YOUR_HOST_IP> --restart

After this (and a gateway rule blocking the DTU from WAN), the DTU will connect to your
cloud_emu.py instead of Hoymiles. Revert with:
  python set_server.py ... --server datana.hoymiles.com --dns 223.5.5.5
"""
import argparse
import asyncio
import time

from hoymiles_wifi.dtu import DTU
from hoymiles_wifi.const import CMD_SET_CONFIG
from hoymiles_wifi.protobuf import SetConfig_pb2
from hoymiles_wifi.utils import initialize_set_config


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="10.10.100.254")
    ap.add_argument("--local-addr", default=None)
    ap.add_argument("--dns", default=None, help="cable DNS to set (e.g. your host IP)")
    ap.add_argument("--server", default=None, help="server_domain_name to set")
    ap.add_argument("--restart", action="store_true", help="reboot the DTU afterwards")
    a = ap.parse_args()

    dtu = DTU(a.host, local_addr=a.local_addr)
    cfg = await dtu.async_get_config()
    if cfg is None:
        print("Could not read DTU config — are you joined to the DTU AP?")
        return

    req = initialize_set_config(cfg)
    req.time = int(time.time())
    req.offset = 0
    req.app_page = 1
    if a.dns:
        o = [int(x) for x in a.dns.split(".")]
        req.cable_dns_0, req.cable_dns_1, req.cable_dns_2, req.cable_dns_3 = o
        print("set cable_dns ->", a.dns)
    if a.server:
        req.server_domain_name = a.server.encode()
        print("set server_domain_name ->", a.server)

    res = await dtu.async_send_request(CMD_SET_CONFIG, req, SetConfig_pb2.SetConfigReqDTO)
    print("SetConfig ->", "error_code", getattr(res, "error_code", "?") if res else "no response")
    if a.restart:
        r = await dtu.async_restart_dtu()
        print("restart ->", "sent" if r else "no response")


if __name__ == "__main__":
    asyncio.run(main())
