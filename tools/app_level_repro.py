#!/usr/bin/env python3
"""Drives the REAL WinKeyer class (not a reimplementation) headlessly
against the real WK-mini, to find out whether the operator's two
reported triggers — app startup, and "changing the spinner" — actually
*cause* the "is open but WinKeyer is not responding" warning, or whether
its recurrence is just the autonomous exponential-backoff reconnect loop
(deviation-log.md #8) running on its own schedule and coinciding with
whatever the operator was doing at the time.

tools/serial_isolation_diagnostic.py already proved the raw pyserial
layer is 100% reliable on this hardware (8/8 clean trials, ~0.10s
response time) right after the stuck app instance was quit — this script
instead exercises the actual Qt code paths (QTimer, signal/slot wiring,
close()-then-immediately-reopen with zero settle gap in host_init())
that the isolated script doesn't touch, to see if THOSE reproduce it.

Runs QT_QPA_PLATFORM=offscreen so no window appears on screen. Uses an
isolated KEYER_MAC_CONFIG_PATH so it never touches the operator's real
~/.keyer-mac.json. Never calls send()/sendblended()/tuneon (keying).

Usage: python3 tools/app_level_repro.py
"""

import logging
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp_config = tempfile.NamedTemporaryFile(prefix="keyer_mac_repro_", suffix=".json", delete=False)
_tmp_config.close()
os.unlink(_tmp_config.name)  # loadsaved() must see "no file" to fall back to auto-detected device
os.environ["KEYER_MAC_CONFIG_PATH"] = _tmp_config.name

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

captured = []  # (monotonic_ts, levelname, message)


class _CaptureHandler(logging.Handler):
    def emit(self, record):
        captured.append((time.monotonic(), record.levelname, record.getMessage()))


logging.getLogger().addHandler(_CaptureHandler())

from PyQt6.QtWidgets import QApplication  # noqa: E402
from keyer_mac.__main__ import WinKeyer  # noqa: E402


def pump(app: QApplication, duration_s: float, label: str) -> None:
    """Drives the real Qt event loop (so timer2's 100ms poll and any
    QTimer-scheduled reconnect actually fire) without app.exec()'s
    blocking main loop."""
    print(f"  pumping event loop for {duration_s:.1f}s ({label})...")
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)


def warnings_since(t0: float) -> list:
    return [(ts - t0, msg) for ts, level, msg in captured if level == "WARNING" and ts >= t0]


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    keyer = WinKeyer()
    print(f"Target device (auto-selected/loaded): {keyer.device}")

    print("\n== Phase 1: cold start (mirrors main()) ==")
    t0 = time.monotonic()
    keyer.host_init()
    pump(app, 3.0, "post-cold-start baseline")
    w = warnings_since(t0)
    print(f"  warnings in first 3s after host_init(): {len(w)}")
    for dt, msg in w:
        print(f"    +{dt:.2f}s  {msg}")

    print("\n== Phase 2: idle autonomous behavior, no interaction (10s) ==")
    t1 = time.monotonic()
    pump(app, 10.0, "idle, watching for autonomous backoff-driven warnings")
    w = warnings_since(t1)
    print(f"  warnings in 10s of pure idle: {len(w)}")
    for dt, msg in w:
        print(f"    +{dt:.2f}s  {msg}")
    if w:
        print("  -> device is still failing/retrying on its own backoff "
              "schedule, unprompted by any UI interaction")
    else:
        print("  -> quiet: no autonomous warnings while idle")

    print("\n== Phase 3: change spinBox_speed (the literal QSpinBox widget) ==")
    t2 = time.monotonic()
    print(f"  current speed: {keyer.spinBox_speed.value()}")
    new_speed = 30 if keyer.spinBox_speed.value() != 30 else 25
    keyer.spinBox_speed.setValue(new_speed)  # fires valueChanged -> spinboxspeed()
    pump(app, 6.0, "watching for warnings after spinbox speed change")
    w = warnings_since(t2)
    print(f"  warnings in 6s after spinbox change: {len(w)}")
    for dt, msg in w:
        print(f"    +{dt:.2f}s  {msg}")
    print("  (code path: spinboxspeed() -> setspeed() -> _port_write() only; "
          "no call to host_init() anywhere in this chain per static read of "
          "__main__.py — any warning here would be the autonomous backoff "
          "schedule coinciding, not a direct causal link)")

    print("\n== Phase 4: reselect device combo box (editingFinished, matches "
          "clicking into the editable field and confirming — same text, no "
          "actual change) ==")
    t3 = time.monotonic()
    keyer.comboBox_device.setCurrentText(keyer.device)
    keyer.comboBox_device.lineEdit().editingFinished.emit()  # -> change_serial() -> host_init()
    pump(app, 6.0, "watching for warnings after combo-box reselect")
    w = warnings_since(t3)
    print(f"  warnings in 6s after combo-box reselect: {len(w)}")
    for dt, msg in w:
        print(f"    +{dt:.2f}s  {msg}")
    print("  (code path: change_serial() -> host_init() unconditionally, "
          "which does self.port.close() immediately followed by a new "
          "serial.Serial().open() with ZERO delay between them — the one "
          "close/reopen-race variant the isolated diagnostic script did "
          "NOT test, since it always left a gap between trials)")

    print("\n== Phase 5: rapid-fire combo-box reselect x15, zero gap between "
          "cycles (stresses the close/reopen race under repetition, not "
          "just once) ==")
    t4 = time.monotonic()
    for i in range(1, 16):
        keyer.comboBox_device.setCurrentText(keyer.device)
        keyer.comboBox_device.lineEdit().editingFinished.emit()
        app.processEvents()
    pump(app, 4.0, "settle after rapid-fire cycling")
    w = warnings_since(t4)
    print(f"  warnings across 15 rapid-fire cycles + 4s settle: {len(w)}")
    for dt, msg in w:
        print(f"    +{dt:.2f}s  {msg}")

    # Not keyer._shutdown(): it calls the module-level `app.quit()` global in
    # keyer_mac.__main__, which is only ever set by that module's own main()
    # and stays None here — an unrelated pre-existing gap, out of scope for
    # this repro. Tear down directly instead.
    keyer.timer2.stop()
    if keyer.port and hasattr(keyer.port, "close"):
        keyer.port.close()
    if os.path.exists(_tmp_config.name):
        os.unlink(_tmp_config.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
