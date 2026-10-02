#!/usr/bin/env python3
"""Stage 4 live checks, one function per feature, against the real WK-mini
with the real MainWindow (offscreen). KEYS THE RADIO: operator confirmed
100 mW and no antenna on 2026-10-02. The keyer-mac app window must be closed.
Config is redirected to a temp file.

Usage: python3 tools/live_stage4.py 4.1 [4.2 ...]
"""

import logging
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

logging.basicConfig(level=logging.WARNING, format="  [log %(asctime)s.%(msecs)03d] %(message)s", datefmt="%H:%M:%S")
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
    print("  [start window]", flush=True)
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


def check_4_2() -> bool:
    w = start()
    texts = ["E", "T", "I", "M", "A"]
    for i, t in enumerate(texts):
        w.msg_fields[i].setText(t)
    w.message.clear_all()
    for i in range(5):
        w.msg_buttons[i].click()
    ok1 = wait_until(lambda: echo_text(w) == "ETIMA", 10, "echo ETIMA")
    print(f"  pressed msg 1-5 -> echo {echo_text(w)!r}: {'PASS' if ok1 else 'FAIL'}")
    w.shutdown()
    w2 = MainWindow(cfg=config.load())            # relaunch: fields come back from the file
    ok2 = [f.text() for f in w2.msg_fields] == texts
    print(f"  relaunch restores {[f.text() for f in w2.msg_fields]}: {'PASS' if ok2 else 'FAIL'}")
    w2.shutdown()
    return ok1 and ok2


def check_4_3() -> bool:
    ok = True
    fresh = config.load()
    w = start()
    ok0 = w.speed_box.currentData() == 20 and fresh["speed"] == 20
    print(f"  fresh file -> dropdown shows {w.speed_box.currentData()} (expect 20): {'PASS' if ok0 else 'FAIL'}")
    ok = ok and ok0
    written = []
    port = w.worker.keyer.port
    real_write = port.write
    port.write = lambda data: (written.append(bytes(data)), real_write(data))[1]
    for wpm in (6, 20, 34):
        w.speed_box.setCurrentIndex(w.speed_box.findData(wpm))
        good = wait_until(lambda wpm=wpm: bytes([2, wpm]) in written, 3, f"02 {wpm:02x} written")
        saved = config.load()["speed"] == wpm
        print(f"  chose {wpm}: wrote 02 {wpm:02x} {good}, saved {saved}: {'PASS' if good and saved else 'FAIL'}")
        ok = ok and good and saved
    w.shutdown()
    w2 = MainWindow(cfg=config.load())
    ok3 = w2.speed_box.currentData() == 34
    print(f"  relaunch shows {w2.speed_box.currentData()} (expect 34): {'PASS' if ok3 else 'FAIL'}")
    w2.shutdown()
    # reconnect re-sends the saved speed: start a fresh window and read the connect bytes
    w3 = MainWindow(cfg=config.load())
    w3.show()
    w3.start_scan()
    wait_until(lambda: w3.result == "found", 10, "found")
    ok4 = "34 WPM" in w3.lines[-1]
    print(f"  next connect reports {w3.lines[-1]!r}: {'PASS' if ok4 else 'FAIL'}")
    w3.speed_box.setCurrentIndex(w3.speed_box.findData(20))      # leave the keyer at 20
    QTest.qWait(300)
    w3.shutdown()
    return ok and ok3 and ok4


CHECKS = {"4.1": check_4_1, "4.2": check_4_2, "4.3": check_4_3}


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
