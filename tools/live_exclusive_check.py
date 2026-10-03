#!/usr/bin/env python3
"""Live check: while ANOTHER keyer-mac window holds the keyer, a second open is
refused at once with the plain "in use by another program" message.

Needs a running keyer-mac window (it must be this build, which opens the port
exclusively). Opens nothing if refused, so the running window is not disturbed.
Run with no window open and it just reports that the port was free.

Usage: python3 tools/live_exclusive_check.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import serial

from keyer_mac import ports, winkeyer


def main() -> int:
    order = ports.probe_order(ports.list_ports())
    if not order:
        print("FAIL: no WK-mini found")
        return 1
    start = time.monotonic()
    try:
        port = winkeyer.open_port(order[0])
    except serial.SerialException as exc:
        ms = (time.monotonic() - start) * 1000
        ok = winkeyer.port_in_use(exc) and ms < 500
        print(f"refused in {ms:.0f} ms: {winkeyer.describe_open_error(order[0], exc)}")
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1
    port.close()
    print("port was free (no other window running): nothing to check; start keyer-mac first")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
