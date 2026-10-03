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
import time
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


def start(**kw) -> MainWindow:
    print("  [start window]", flush=True)
    w = MainWindow(cfg=config.load(), **kw)
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


def measured_gap_ms(w, seconds: float) -> float:
    """Average gap between echoed characters, measured through the real window."""
    marks = []                                    # (time, characters received so far)
    count = [0]

    def on_echo(text):
        count[0] += len(text)
        marks.append((time.monotonic(), count[0]))

    w.worker.echoed.connect(on_echo)
    w.free_text.clear()
    w.free_text.insertPlainText("EEEEEEEEEEEE")        # 12 E's -> 11 gaps (poll jitter is 100 ms)
    wait_until(lambda: count[0] >= 12, seconds, "12 echoes")
    w.worker.echoed.disconnect(on_echo)
    if len(marks) < 2 or marks[-1][1] == marks[0][1]:
        return float("nan")
    return (marks[-1][0] - marks[0][0]) * 1000 / (marks[-1][1] - marks[0][1])


def check_marks() -> bool:
    """'... ' after each sent message; Enter in free text is a marker, never a byte."""
    w = start()
    written = []
    port = w.worker.keyer.port
    real_write = port.write
    port.write = lambda data: (written.append(bytes(data)), real_write(data))[1]
    ok = True

    def expect(label, want, seconds=8):
        nonlocal ok
        good = wait_until(lambda: echo_text(w) == want, seconds, label)
        print(f"  {label}: echo {echo_text(w)!r} (want {want!r}): {'PASS' if good else 'FAIL'}")
        ok = ok and good

    w.msg_fields[0].setText("E"); w.msg_fields[1].setText("T")
    w.message.clear_all(); w._reset_message_counts()
    w.msg_buttons[0].click(); w.msg_buttons[1].click()
    expect("msg 1 then msg 2", "E... T... ")
    QTest.qWait(500)
    w.message.clear_all(); w._reset_message_counts(); written.clear()
    for chunk in ("E", "\n", "T"):
        w.free_text.insertPlainText(chunk)
        QTest.qWait(150)
    expect("free text E, Enter, T", "E... T")
    bad = [b for b in written if b"\x0a" in b or b"\x0d" in b]
    print(f"  no 0x0a / 0x0d byte written for Enter: {'PASS' if not bad else 'FAIL ' + str(bad)}")
    ok = ok and not bad
    QTest.qWait(800)
    w.message.clear_all(); w._reset_message_counts(); w.free_text.clear()
    w._bridge_send_string("N")
    expect("XMLRPC-style string 'N'", "N... ")
    w.shutdown()
    return ok


def check_speed_effect() -> bool:
    """The functional check that was missing: the dropdown really changes the CW speed."""
    w = start()
    ok = True
    for wpm in (20, 34, 6, 20):
        w.speed_box.setCurrentIndex(w.speed_box.findData(wpm))
        QTest.qWait(300)
        want = 4 * 1200 / wpm
        got = measured_gap_ms(w, 3 + 12 * want / 1000)
        good = abs(got - want) / want < 0.25
        ok = ok and good
        print(f"  dropdown {wpm}: measured gap {got:.0f} ms, expected {want:.0f} ms: {'PASS' if good else 'FAIL'}")
        QTest.qWait(500)
    w.shutdown()
    return ok


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


def check_4_4() -> bool:
    from keyer_mac.settings import Settings

    w = start()
    written = []
    port = w.worker.keyer.port
    real_write = port.write
    port.write = lambda data: (written.append(bytes(data)), real_write(data))[1]

    def accept_iambic_a(self):
        self.key_mode.setCurrentText("Iambic A")
        self.save_changes()
        return 1

    def cancel_bug_mode(self):
        self.key_mode.setCurrentText("Bug Mode")
        return 0

    orig = Settings.exec
    Settings.exec = accept_iambic_a
    w.gear.click()
    want = bytes([0x0E, int(w.cfg["mode_register"], 2)])
    ok1 = wait_until(lambda: want in written, 3, "mode register written") and config.load()["mode_register"] == w.cfg["mode_register"]
    print(f"  Save as Iambic A -> wrote {want.hex(' ')}, saved {config.load()['mode_register']}: {'PASS' if ok1 else 'FAIL'}")
    written.clear()
    Settings.exec = cancel_bug_mode
    before = dict(w.cfg)
    w.gear.click()
    QTest.qWait(500)
    ok2 = not any(b[:1] == b"\x0e" for b in written) and w.cfg == before
    print(f"  Cancel after editing -> nothing written, config unchanged: {'PASS' if ok2 else 'FAIL'}")
    Settings.exec = orig
    w.apply_mode_register("11001110")                  # leave the keyer at the default
    QTest.qWait(300)
    w.shutdown()
    return ok1 and ok2


def check_port() -> bool:
    w = start()
    n = len(w.lines)
    idx = w.port_box.findText("/dev/cu.usbserial-8330")
    w.port_box.setCurrentIndex(idx)
    w.port_box.activated.emit(idx)                     # user picks the port
    QTest.qWait(1500)
    ok1 = len(w.lines) == n and w.result == "found"
    print(f"  pick the already-connected port -> no rescan, still connected: {'PASS' if ok1 else 'FAIL'}")
    n = len(w.lines)
    w.port_box.lineEdit().setText("/dev/cu.does-not-exist")
    w.port_box.lineEdit().editingFinished.emit()       # typed bogus port + Enter
    ok2 = wait_until(lambda: w.result == "found" and any(l.startswith("Scanning") for l in w.lines[n:]), 14, "found despite bogus port")
    print(f"  typed bogus port -> falls through to the WK-mini: {'PASS' if ok2 else 'FAIL'}")
    w.shutdown()
    return ok1 and ok2


def check_4_5() -> bool:
    import xmlrpc.client

    w = start(start_bridge=True, bridge_host="127.0.0.1")     # loopback: no firewall prompt
    p = xmlrpc.client.ServerProxy(f"http://127.0.0.1:{w.bridge.port}")
    written = []
    port = w.worker.keyer.port
    real_write = port.write
    port.write = lambda data: (written.append(bytes(data)), real_write(data))[1]
    results = []

    def check(label, ok):
        results.append(ok)
        print(f"  {label}: {'PASS' if ok else 'FAIL'}")

    w.message.clear_all()
    p.k1elsendstring("E")
    check("k1elsendstring('E') -> echoed E", wait_until(lambda: echo_text(w) == "E", 5, "echo E"))
    p.sendblended("AR")
    check("sendblended('AR') -> wrote 1b 41 52", wait_until(lambda: b"\x1bAR" in written, 3, "blended"))
    p.setspeed(24)
    check("setspeed(24) -> wrote 02 18, dropdown shows 24",
          wait_until(lambda: bytes([2, 24]) in written and w.speed_box.currentData() == 24, 3, "setspeed"))
    p.setspeed(20)
    p.tuneon(); QTest.qWait(300); p.tuneoff()
    check("tuneon/tuneoff -> wrote 0b 01 then 0b 00",
          wait_until(lambda: b"\x0b\x01" in written and b"\x0b\x00" in written, 3, "tune")
          and written.index(b"\x0b\x01") < written.index(b"\x0b\x00"))
    # wait until the keyer has been quiet for 2 s so no earlier echo lands in this check
    quiet_since, last = 0, echo_text(w)
    waited = 0
    while quiet_since < 2000 and waited < 12000:
        QTest.qWait(100); waited += 100
        now = echo_text(w)
        quiet_since = quiet_since + 100 if now == last else 0
        last = now
    w.message.clear_all()
    p.k1elsendstring("TTTTTTTT"); QTest.qWait(300); p.clearbuffer()
    QTest.qWait(4500)
    got = echo_text(w)
    check(f"clearbuffer after 8 T's -> fewer than 8 T's sent ({got!r})",
          b"\x0a" in written and got.count("T") < 8)
    w.shutdown()
    return all(results)


CHECKS = {"marks": check_marks, "speed": check_speed_effect, "4.5": check_4_5, "port": check_port, "4.1": check_4_1, "4.2": check_4_2, "4.3": check_4_3, "4.4": check_4_4}


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
