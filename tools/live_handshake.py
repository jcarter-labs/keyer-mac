#!/usr/bin/env python3
"""Task 2.2 live check: keyer_mac.winkeyer connect sequence on the real
WK-mini, N times in a row (default 20), each from a fresh port open.

Per cycle: open port -> host_open (version byte) -> echo test -> host_close
-> close port -> 0.3 s pad. Administrative commands only; never keys the
radio. The keyer-mac app window must be closed (it holds the port).

Usage: python3 tools/live_handshake.py [N]
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from keyer_mac import ports, winkeyer


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    order = ports.probe_order(ports.list_ports())
    if not order:
        print("FAIL: no WK-mini candidate found")
        return 1
    device = order[0]
    print(f"device {device}, {n} cycles")
    failures = 0
    for i in range(1, n + 1):
        t0 = time.monotonic()
        port = winkeyer.open_port(device)
        try:
            wk = winkeyer.WinKeyer(port)
            version = wk.host_open()
            echo = wk.echo_test(0x55) if version is not None else False
            wk.host_close()
        finally:
            port.close()
        ok = version is not None and echo
        failures += not ok
        v = "none" if version is None else f"0x{version:02x}"
        print(f"{i:2d}: version={v} echo={echo} {time.monotonic() - t0:.2f}s {'PASS' if ok else 'FAIL'}")
        time.sleep(0.3)
    print(f"\n{'PASS' if not failures else 'FAIL'}: {n - failures}/{n} cycles")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
