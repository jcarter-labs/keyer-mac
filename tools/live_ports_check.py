#!/usr/bin/env python3
"""Task 2.1 live check: run keyer_mac.ports against the real machine.

Pass: the WK-mini is the only candidate, virtual ports are rejected, and
nothing is opened (enumeration only).

Usage: python3 tools/live_ports_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from keyer_mac import ports


def main() -> int:
    found = ports.list_ports()
    print(f"{'device':<36} {'vid':>6} {'pid':>6}  virtual  candidate")
    for p in found:
        vid = "-" if p.vid is None else f"{p.vid:04x}"
        pid = "-" if p.pid is None else f"{p.pid:04x}"
        print(f"{p.device:<36} {vid:>6} {pid:>6}  {str(ports.is_virtual(p)):<7}  {ports.is_winkeyer_candidate(p)}")
    order = ports.probe_order(found)
    print("\nprobe order:", order)
    virtual_devices = {p.device for p in found if ports.is_virtual(p)}
    ok = len(order) == 1 and not (set(order) & virtual_devices)
    print("PASS" if ok else "FAIL", "- exactly one candidate, no virtual port in it")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
