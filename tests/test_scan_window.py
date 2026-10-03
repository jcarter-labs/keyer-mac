"""Masterplan 2.5 / 3.4 (early): countdown, found and missing messages, and
a stalled port does not stop the 1 s UI ticks. Fake ports only."""

import time
from collections import namedtuple

from keyer_mac import config
from keyer_mac.ui import MISSING_TEXT, MainWindow
from keyer_mac.worker import Worker

P = namedtuple("P", "device vid pid")
WK = P("/dev/cu.usbserial-TEST", 0x1A86, 0x7523)


class FakePort:
    """Answers host open with 0x1f and echo test with the byte sent."""

    def __init__(self, delay_s=0.0):
        self.delay_s = delay_s
        self.written, self._inbox, self.closed = [], b"", False

    def write(self, data):
        data = bytes(data)
        self.written.append(data)
        if data == b"\x00\x02":
            time.sleep(self.delay_s)
            self._inbox += b"\x1f"
        elif data[:2] == b"\x00\x04":
            self._inbox += data[2:3]

    def read(self, n):
        out, self._inbox = self._inbox[:n], self._inbox[n:]
        return out

    def reset_input_buffer(self):
        self._inbox = b""

    def close(self):
        self.closed = True


def make_window(ports, delay_s=0.0):
    holder = {}

    def open_port(device):
        holder["port"] = FakePort(delay_s)
        return holder["port"]

    w = MainWindow(Worker(open_port=open_port, list_ports=lambda: ports), cfg=config.defaults())
    # fake serial waits: skip the real 1 s reset wait inside host_open
    return w, holder


def test_missing_when_no_candidate(qtbot):
    w, _ = make_window([])
    qtbot.addWidget(w)
    with qtbot.waitSignal(w.worker.missing, timeout=3000):
        w.start_scan()
    qtbot.waitUntil(lambda: w.result == "missing", timeout=2000)
    assert w.lines[0] == "Scanning for keyer… 8"
    assert MISSING_TEXT in w.lines
    w.shutdown()


def test_found_shows_version_port_and_speed_sent(qtbot):
    w, holder = make_window([WK])
    qtbot.addWidget(w)
    w.start_scan()
    qtbot.waitUntil(lambda: w.result == "found", timeout=5000)
    assert w.lines[-1] == "Keyer found: WinKeyer v3.1 on /dev/cu.usbserial-TEST, 20 WPM"
    written = holder["port"].written
    assert b"\x0e\xce" in written and b"\x02\x14" in written       # mode, speed
    assert written.index(b"\x0e\xce") < written.index(b"\x02\x14")  # in order
    w.shutdown()


def test_countdown_keeps_ticking_while_the_port_stalls(qtbot):
    w, _ = make_window([WK], delay_s=2.5)   # host open answers 2.5 s late
    qtbot.addWidget(w)
    w.start_scan()
    qtbot.waitUntil(lambda: w.result is not None, timeout=8000)
    ticks = [l for l in w.lines if l.startswith("Scanning")]
    assert ticks[:3] == ["Scanning for keyer… 8", "Scanning for keyer… 7", "Scanning for keyer… 6"]
    w.shutdown()


def test_failures_and_retries_are_printed_with_a_time_stamp(qtbot):
    import re
    w, _ = make_window([])
    qtbot.addWidget(w)
    w.start_scan()
    qtbot.waitUntil(lambda: w.result == "missing", timeout=3000)
    stamped = [l for l in w.lines if re.match(r"^\d\d:\d\d:\d\d ", l)]
    assert any("No WinKeyer-mini" in l for l in stamped)
    assert any(l.endswith("Retrying in 1 s") for l in stamped)
    w.shutdown()
