#!/usr/bin/env python3
"""Does a speed change actually change the CW speed? (Functional check, live.)

The keyer echoes each character as it sends it, so the gap between echoed
characters is the real sending speed. Sends "EEEEEE" (1 dit + 3-unit gap =
4 units per character; unit = 1200/WPM ms) at several speeds in one session,
the way the app does, and compares the measured gap with the expected one.
KEYS THE RADIO (operator: 100 mW, no antenna). The app window must be closed.

Usage: python3 tools/live_speed_diagnostic.py [extra-setup-bytes-hex ...]
"""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from keyer_mac import ports, winkeyer


def measure(wk, port, text="EEEEEE", wait=6.0):
    """Send text; return the gaps (ms) between successive echoed characters."""
    port.reset_input_buffer()
    wk.send_text(text)
    stamps, end = [], time.monotonic() + wait
    while time.monotonic() < end and len(stamps) < len(text):
        b = port.read(1)
        if b and 0x20 <= b[0] < 0x80:
            stamps.append(time.monotonic())
        elif not b:
            time.sleep(0.001)
    return [round((b - a) * 1000) for a, b in zip(stamps, stamps[1:])]


def main() -> int:
    extra = [bytes.fromhex(a) for a in sys.argv[1:]]
    order = ports.probe_order(ports.list_ports())
    port = winkeyer.open_port(order[0], timeout=0)
    wk = winkeyer.WinKeyer(port)
    try:
        if wk.host_open() is None or not wk.initialize():
            print("FAIL: keyer did not initialize")
            return 1
        for blob in extra:
            wk._write(blob)
            print("extra setup written:", blob.hex(" "))
        print(f"{'speed':>6} {'expected gap':>13} {'measured gaps (ms)':<40} {'median':>7}")
        results = []
        for wpm in (20, 34, 6, 20):
            wk.set_speed(wpm)
            time.sleep(0.2)
            gaps = measure(wk, port, wait=2.0 + 6 * 4 * 1200 / wpm / 1000)
            expected = 4 * 1200 / wpm
            med = statistics.median(gaps) if gaps else float("nan")
            results.append((wpm, expected, med))
            print(f"{wpm:>6} {expected:>11.0f}ms {str(gaps):<40} {med:>7.0f}")
            time.sleep(0.5)
        ok = all(abs(med - exp) / exp < 0.25 for _, exp, med in results)
        print("PASS: measured speed follows the setting" if ok else "FAIL: measured speed does NOT follow the setting")
        wk.host_close()
        return 0 if ok else 1
    finally:
        port.close()


if __name__ == "__main__":
    raise SystemExit(main())
