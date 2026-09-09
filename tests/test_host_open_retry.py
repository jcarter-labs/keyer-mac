"""Logic-only tests for host_open()'s retry loop and host_init()'s
close-reopen settle delay, added after tools/app_level_repro.py Phase 5
reproduced "is open but WinKeyer is not responding" against real hardware
via rapid device-reselection (troubleshooting-transcript.md turns 19-30).
No hardware needed: serial.Serial is monkeypatched out, matching
test_reconnect_backoff.py's pattern.

Covers:
- a transient no-response on the first attempt recovers silently (no log,
  no on-screen message) if a later attempt gets a version back;
- exhausting every attempt still logs/shows exactly once, not per attempt;
- the close-reopen settle delay only fires when there's a previous port
  to close, not on the very first open.
"""

import time

import pytest


def make_keyer(monkeypatch, tmp_path):
    """Same seam as test_reconnect_backoff.py's make_keyer(): a WinKeyer
    with no real serial.Serial() constructed and time.sleep() replaced
    (callers install their own spy/no-op after this)."""
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "config.json"))
    from keyer_mac.__main__ import WinKeyer

    win = WinKeyer()
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)
    return win


class ScriptedSerial:
    """Like test_reconnect_backoff.py's FakeSerialCtor, but read() returns
    a different value each call, scripted in advance — one entry per
    _host_open_attempt() the test expects to happen."""

    def __init__(self, version_sequence):
        self._version_sequence = list(version_sequence)
        self.read_calls = 0
        self.writes = []
        self.is_open = True
        self.port = None
        self.baudrate = None
        self.bytesize = None
        self.parity = None
        self.stopbits = None
        self.dsrdtr = None
        self.rtscts = None
        self.timeout = None
        self.write_timeout = None

    def open(self):
        pass

    def close(self):
        pass

    def write(self, data):
        self.writes.append(data)

    def read(self, size=1):
        self.read_calls += 1
        if not self._version_sequence:
            return b""
        return self._version_sequence.pop(0)


def install_scripted_serial(monkeypatch, version_sequence):
    ctor = ScriptedSerial(version_sequence)
    monkeypatch.setattr("keyer_mac.__main__.serial.Serial", lambda: ctor)
    return ctor


def test_host_open_recovers_from_transient_no_response(monkeypatch, tmp_path, caplog):
    """First attempt gets nothing back (the close-reopen race), second
    attempt gets the version — host_open() must succeed silently: no
    warning logged, no failure registered, exactly the two read() calls
    the retry loop is supposed to make."""
    win = make_keyer(monkeypatch, tmp_path)
    fake = install_scripted_serial(monkeypatch, [b"", b"WK\r"])

    with caplog.at_level("WARNING"):
        win.host_init()

    assert win.version == b"WK\r"
    assert fake.read_calls == 2
    assert win._reconnect_attempt == 0  # success path, no failure registered
    assert not any("not responding" in r.message for r in caplog.records)


def test_host_open_gives_up_after_max_attempts_and_logs_once(monkeypatch, tmp_path, caplog):
    """Every attempt comes back empty — host_open() must stop after
    _host_open_max_attempts, log/show the warning exactly once (not once
    per attempt), and register the failure exactly once."""
    win = make_keyer(monkeypatch, tmp_path)
    fake = install_scripted_serial(monkeypatch, [])  # read() always returns b""

    with caplog.at_level("WARNING"):
        win.host_init()

    assert win.version == b""
    assert fake.read_calls == win._host_open_max_attempts
    not_responding = [r for r in caplog.records if "not responding" in r.message]
    assert len(not_responding) == 1
    assert win._reconnect_attempt == 1


def test_host_open_pushes_displayed_speed_to_device_on_success(monkeypatch, tmp_path):
    """__init__'s spinBox_speed.setValue(20) fires before self.port
    exists, so setspeed()'s hasattr(self.port, "write") guard silently
    drops it — the WinKeyer never got a setspeed command and kept
    running at its own power-on speed until the operator happened to
    touch the spinbox. A successful host_open() must now push the
    displayed value (default 20 WPM) to the device itself."""
    win = make_keyer(monkeypatch, tmp_path)
    assert win.spinBox_speed.value() == 20
    fake = install_scripted_serial(monkeypatch, [b"WK\r"])

    win.host_init()

    expected = chr(2).encode() + chr(20).encode()  # setspeed()'s command format
    assert expected in fake.writes


def test_close_reopen_settle_delay_only_when_reopening(monkeypatch, tmp_path):
    """The settle delay belongs between closing a previous port and
    opening the new one — it must not fire on the very first open (no
    previous port to race against)."""
    win = make_keyer(monkeypatch, tmp_path)
    install_scripted_serial(monkeypatch, [b"WK\r"])

    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    assert win.port is None
    win.host_init()  # first-ever open: no prior port to close
    assert win._close_reopen_settle_s not in sleeps

    sleeps.clear()
    install_scripted_serial(monkeypatch, [b"WK\r"])
    win.host_init()  # reopen: a previous (fake) port exists and gets closed
    assert win._close_reopen_settle_s in sleeps
