#!/usr/bin/env python3
"""Task 2.4 live check: a real XMLRPC client call keys the real WK-mini.

Sends ONE dit ("E") at 20 WPM, which keys whatever is on the key jack; the
operator confirmed 100 mW and no antenna on 2026-10-02. Pass: the call
returns within 1 s and the keyer echoes "E" (status bytes >= 0x80 ignored). The keyer-mac app must be closed.

Usage: python3 tools/live_xmlrpc.py
"""

import sys
import time
import xmlrpc.client
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QCoreApplication, Qt

from keyer_mac import ports, winkeyer
from keyer_mac.bridge import Bridge


def main() -> int:
    app = QCoreApplication([])
    order = ports.probe_order(ports.list_ports())
    if not order:
        print("FAIL: no WK-mini found")
        return 1
    port = winkeyer.open_port(order[0])
    wk = winkeyer.WinKeyer(port)
    try:
        if wk.host_open() is None or not wk.initialize():
            print("FAIL: keyer did not initialize")
            return 1
        bridge = Bridge(host="127.0.0.1", port=8000)
        if not bridge.start():
            print("FAIL: could not bind port 8000")
            return 1
        bridge.send_string.connect(wk.send_text, Qt.ConnectionType.DirectConnection)
        port.reset_input_buffer()
        t0 = time.monotonic()
        result = xmlrpc.client.ServerProxy("http://127.0.0.1:8000").k1elsendstring("E")
        call_s = time.monotonic() - t0
        # status bytes (0xc0-0xff) arrive around the echo; collect for 2 s
        got = b""
        end = time.monotonic() + 2.0
        while time.monotonic() < end:
            got += port.read(8)
            time.sleep(0.02)
        echoed = bytes(b for b in got if b < 0x80)
        bridge.stop()
        ok = result is True and call_s < 1.0 and echoed == b"E"
        print(f"call returned {result!r} in {call_s * 1000:.0f} ms; bytes back {got.hex(' ')}; echoed {echoed!r}")
        print("PASS" if ok else "FAIL")
        wk.host_close()
        return 0 if ok else 1
    finally:
        port.close()


if __name__ == "__main__":
    raise SystemExit(main())
