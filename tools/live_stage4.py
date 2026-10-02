#!/usr/bin/env python3
"""Stage 4 live checks, one function per feature, against the real WK-mini
with the real MainWindow (offscreen). KEYS THE RADIO: operator confirmed
100 mW and no antenna on 2026-10-02. The keyer-mac app window must be closed.
Config is redirected to a temp file.

Usage: python3 tools/live_stage4.py 4.1 [4.2 ...]
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CFG = Path(tempfile.mkdtemp(prefix="keyer_mac_live_")) / "cfg.json"
os.environ["KEYER_MAC_CONFIG_PATH"] = str(CFG)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from keyer_mac import config
from keyer_mac.ui import MainWindow

app = QApplication([])


def wait_until(pred, seconds, label):
    waited = 0
    while waited < seconds * 1000:
        if pred():
            return True
        QTest.qWait(50)
        waited += 50
    print(f"  timeout waiting for: {label}")
    return False


def start() -> MainWindow:
    w = MainWindow(cfg=config.load())
    w.show()
    w.start_scan()
    assert wait_until(lambda: w.result == "found", 10, "keyer found"), w.lines
    return w


def echo_text(w) -> str:
    return "".join(l for l, k in zip(w.message.lines, w.message.kinds) if k == "echo")


def check_4_1() -> bool:
    w = start()
    for ch in "TEST":
        w.free_text.insertPlainText(ch)
        QTest.qWait(120)
    ok1 = wait_until(lambda: echo_text(w) == "TEST", 8, "echo TEST")
    print(f"  typed TEST -> Message box echo {echo_text(w)!r}: {'PASS' if ok1 else 'FAIL'}")
    # backspace erases unsent characters: queue 8 A's, delete the last 3 at once
    w.message.clear_all()
    w.free_text.clear()
    w.free_text.insertPlainText("AAAAAAAA")
    QTest.qWait(150)
    for _ in range(3):
        w.free_text.textCursor().deletePreviousChar()
    QTest.qWait(7000)
    got = echo_text(w)
    ok2 = got.count("A") == 5 and set(got) <= {"A"}
    print(f"  typed 8 A, deleted 3 unsent -> echo {got!r}: {'PASS' if ok2 else 'FAIL'}")
    w.shutdown()
    return ok1 and ok2


CHECKS = {"4.1": check_4_1}


def main() -> int:
    wanted = sys.argv[1:] or list(CHECKS)
    failed = 0
    for key in wanted:
        print(f"{key}:")
        ok = CHECKS[key]()
        failed += not ok
    print("\nPASS" if not failed else "\nFAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
