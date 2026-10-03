#!/usr/bin/env python3
"""Task 5.2 live smoke: N cold starts (fresh processes) of the real app
against the real WK-mini (default 5), then one measured speed check
(tools/live_speed_diagnostic.py).

Pass per start: the first line is "Scanning for keyer… 8", countdown lines
only ever step down by one, and the last line is "Keyer found: WinKeyer
vX.Y on <port>, 20 WPM". Runs offscreen; the keyer-mac app window must be
closed.

Usage: python3 tools/live_smoke.py [N]
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOUND = re.compile(r"^Keyer found: WinKeyer v\d+\.\d+ on /dev/cu\.usbserial-\S+, 20 WPM$")
TICK = re.compile(r"^Scanning for keyer… (\d+)$")


def one_start(env) -> tuple[bool, list[str], float]:
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, "-m", "keyer_mac"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=40)
    lines = [l for l in r.stdout.splitlines() if l]
    ticks = [int(m.group(1)) for l in lines if (m := TICK.match(l))]
    lines = [l for l in lines if not l.startswith("qt.qpa")]
    ok = (bool(lines) and lines[0] == "Scanning for keyer… 8" and bool(FOUND.match(lines[-1]))
          and not any(re.match(r"^\d\d:\d\d:\d\d ", l) for l in lines)       # no diagnostics
          and all(a - b == 1 for a, b in zip(ticks, ticks[1:])) and r.returncode == 0)
    return ok, lines, time.monotonic() - t0


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    env = dict(os.environ, KEYER_MAC_AUTOQUIT="1", QT_QPA_PLATFORM="offscreen",
               KEYER_MAC_CONFIG_PATH="/tmp/keyer_mac_live_smoke.json", KEYER_MAC_BRIDGE_HOST="127.0.0.1")
    failures = 0
    for i in range(1, n + 1):
        ok, lines, secs = one_start(env)
        failures += not ok
        print(f"{i:2d}: {'PASS' if ok else 'FAIL'} {secs:.1f}s  {' | '.join(lines)}")
        time.sleep(0.3)
    print(f"\n{'PASS' if not failures else 'FAIL'}: {n - failures}/{n} cold starts")
    # the speed really changes (echo timing); keys the radio briefly: 100 mW, no antenna
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "live_speed_diagnostic.py")],
                       capture_output=True, text=True, timeout=120)
    print(r.stdout.strip())
    return 1 if (failures or r.returncode) else 0


if __name__ == "__main__":
    raise SystemExit(main())
