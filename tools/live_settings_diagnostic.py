#!/usr/bin/env python3
"""Task 2.3 live diagnostic: can the WK-mini report its settings back?

Sends only speed (02) and read-only queries; never the admin commands that
write EEPROM (0D) or start a firmware update (10). Never keys the radio.
The keyer-mac app window must be closed.

Result on the operator's WK-mini (firmware 0x1f), 2026-10-02:
  admin 00 07 (after set 20 and set 30): no reply
  pot query 07 (after set 20 and set 30): 0x8c both times (independent of speed)
  status 15: 0xc0
=> no tested read path reflects the speed that was set: speed readback is
   NOT possible. The Spec's fallback applies: verify = writes succeeded and
   the echo test passed.

Usage: python3 tools/live_settings_diagnostic.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from keyer_mac import ports, winkeyer


def main() -> int:
    order = ports.probe_order(ports.list_ports())
    if not order:
        print("FAIL: no WK-mini found")
        return 1
    port = winkeyer.open_port(order[0])
    wk = winkeyer.WinKeyer(port)
    try:
        print("version", hex(wk.host_open() or 0))
        replies = {}
        for wpm in (20, 30):
            wk._write(bytes([2, wpm]))
            time.sleep(0.2)
            port.reset_input_buffer()
            wk._write(bytes([0, 7]))
            replies[("admin07", wpm)] = wk._read(32, 1.0)
            port.reset_input_buffer()
            wk._write(bytes([7]))
            replies[("pot", wpm)] = wk._read(1, 0.5)
            print(f"set {wpm}: admin07={replies[('admin07', wpm)].hex(' ') or '-'} pot={replies[('pot', wpm)].hex(' ') or '-'}")
        port.reset_input_buffer()
        wk._write(bytes([0x15]))
        print("status:", wk._read(1, 0.5).hex(" ") or "-")
        reflects = replies[("pot", 20)] != replies[("pot", 30)] or replies[("admin07", 20)] != replies[("admin07", 30)]
        print("speed readback possible:", reflects)
        wk._write(bytes([2, winkeyer.DEFAULT_SPEED]))
        wk.host_close()
    finally:
        port.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
