"""Logic-only tests for the reconnect backoff/settle hardening in
getwaiting()/host_init()/host_open() (deviation-log.md #8). No hardware
needed: a dummy port simulates read/write and error conditions, and
host_init()'s own serial.Serial()/open() calls are monkeypatched out so
these tests never touch a real device.

Covers:
- a narrowed except (serial.SerialException only) so a raised error still
  triggers reconnect the way source's bare except did;
- an in_waiting-but-empty-read race no longer misfires a reconnect;
- a port left as `False` after a failed reopen no longer AttributeErrors
  and spins host_init() every tick — it's retried through the same gate;
- the backoff gate itself: growing spacing on repeated failures, reset on
  success, and no throttling of an explicit/first host_init() call.
"""

import time

import serial
import pytest


class DummyPort:
    """A stand-in serial port. write() is a no-op like test_speed_arbitration's
    DummyPort; read()/in_waiting can be scripted to simulate the conditions
    under test, and is_open reflects the fact that host_init() successfully
    "opened" this dummy.
    """

    def __init__(self, read_bytes=b"", in_waiting=0, is_open=True, read_error=None):
        self._read_bytes = read_bytes
        self.in_waiting = in_waiting
        self.is_open = is_open
        self._read_error = read_error

    def write(self, data):
        pass

    def read(self, size=1):
        if self._read_error is not None:
            raise self._read_error
        data, self._read_bytes = self._read_bytes[:size], self._read_bytes[size:]
        return data

    def close(self):
        pass


def make_keyer(monkeypatch, tmp_path):
    """A WinKeyer with host_init()'s hardware-facing bits stubbed out: no real
    serial.Serial() is constructed, and time.sleep() is a no-op so tests run
    fast despite host_open()'s real sleeps in source.
    """
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "config.json"))
    from keyer_mac.__main__ import WinKeyer

    win = WinKeyer()
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)
    return win


def stub_successful_open(monkeypatch, win, version=b"WK\r"):
    """Make host_init() "open" a fake port that returns `version` for the
    host_open() version read, instead of touching a real serial.Serial().
    host_init() builds serial.Serial(), sets attrs, then calls .open() —
    patch serial.Serial to hand back an object whose open()/close()/write()
    are no-ops and whose read() returns `version`.
    """

    class FakeSerialCtor:
        def __init__(self):
            self.port = None
            self.baudrate = None
            self.bytesize = None
            self.parity = None
            self.stopbits = None
            self.dsrdtr = None
            self.rtscts = None
            self.timeout = None
            self.write_timeout = None
            self.is_open = True

        def open(self):
            pass

        def close(self):
            pass

        def write(self, data):
            pass

        def read(self, size=1):
            return version[:size]

    monkeypatch.setattr("keyer_mac.__main__.serial.Serial", FakeSerialCtor)


def test_stale_read_error_triggers_reconnect_like_source(monkeypatch, tmp_path):
    """A genuine serial.SerialException on read still triggers a reconnect,
    same outcome as source's bare except — just via a narrower catch.
    """
    win = make_keyer(monkeypatch, tmp_path)
    stub_successful_open(monkeypatch, win)

    calls = []
    monkeypatch.setattr(win, "host_init", lambda *a, **k: calls.append((a, k)))

    win.port = DummyPort(in_waiting=1, read_error=serial.SerialException("device gone"))
    win.last_tx_time = time.time()
    win.getwaiting()

    assert len(calls) == 1
    assert calls[0][1] == {"is_reconnect": True}


def test_empty_read_race_does_not_reconnect(monkeypatch, tmp_path):
    """in_waiting > 0 but read(1) comes back empty (a non-blocking-read race,
    not a fault) must not be treated as a disconnect — source's bare except
    would have turned the resulting IndexError into a spurious reconnect.
    """
    win = make_keyer(monkeypatch, tmp_path)

    calls = []
    monkeypatch.setattr(win, "host_init", lambda *a, **k: calls.append((a, k)))

    win.port = DummyPort(read_bytes=b"", in_waiting=1)  # in_waiting lies, read() returns b""
    win.last_tx_time = time.time()
    win.getwaiting()  # must not raise, must not reconnect

    assert calls == []


def test_port_left_false_after_failed_reopen_does_not_spin(monkeypatch, tmp_path):
    """After a failed reopen, self.port is `False` (bool). Source's bare
    except caught the AttributeError from `False.in_waiting` and called
    host_init() again — every 100ms, forever. This must not crash, and must
    route through the same backoff gate rather than firing unconditionally.
    """
    win = make_keyer(monkeypatch, tmp_path)

    calls = []
    monkeypatch.setattr(win, "host_init", lambda *a, **k: calls.append((a, k)))

    win.port = False
    win.getwaiting()  # must not raise AttributeError

    assert len(calls) == 1
    assert calls[0][1] == {"is_reconnect": True}


def test_backoff_gate_suppresses_immediate_retry(monkeypatch, tmp_path):
    """After a registered failure, a reconnect attempt within the backoff
    window must not call host_init() again — this is the fix for the
    reconnect storm (two "not responding" warnings 6s apart cascading via
    getwaiting()'s 100ms poll).
    """
    win = make_keyer(monkeypatch, tmp_path)
    win._register_reconnect_failure()  # simulates a just-failed attempt

    calls = []
    monkeypatch.setattr(win, "host_init", lambda *a, **k: calls.append((a, k)))

    win.port = False
    win.getwaiting()  # still within the backoff window

    assert calls == []  # gated, not called every 100ms tick


def test_backoff_grows_and_caps(monkeypatch, tmp_path):
    """Consecutive failures grow the backoff window exponentially, capped at
    _reconnect_backoff_max_s, so a device that stays gone is polled less and
    less often rather than hammered forever at the same rate.
    """
    win = make_keyer(monkeypatch, tmp_path)
    base = win._reconnect_backoff_base_s
    cap = win._reconnect_backoff_max_s

    before = time.time()
    win._register_reconnect_failure()
    first_wait = win._next_reconnect_time - before
    assert first_wait == pytest.approx(base, abs=0.05)

    before = time.time()
    win._register_reconnect_failure()
    second_wait = win._next_reconnect_time - before
    assert second_wait == pytest.approx(base * 2, abs=0.05)
    assert second_wait > first_wait

    for _ in range(10):  # enough iterations to hit the cap
        win._register_reconnect_failure()
    before = time.time()
    win._register_reconnect_failure()
    capped_wait = win._next_reconnect_time - before
    assert capped_wait == pytest.approx(cap, abs=0.05)


def test_success_resets_backoff_state(monkeypatch, tmp_path):
    """A successful host_open() (non-empty version) clears the failure
    counter and backoff window, so a device that comes back online is
    polled at the normal 100ms cadence again, not left on a long backoff.
    """
    win = make_keyer(monkeypatch, tmp_path)
    win._register_reconnect_failure()
    win._register_reconnect_failure()
    assert win._reconnect_attempt == 2

    win._register_reconnect_success()

    assert win._reconnect_attempt == 0
    assert win._next_reconnect_time == 0.0


def test_explicit_first_host_init_is_not_throttled(monkeypatch, tmp_path):
    """An explicit/first host_init() call (startup, or the user picking a
    device in the combo box) must never be gated by backoff — only
    getwaiting()'s automatic recovery path goes through _attempt_reconnect().
    Verified by confirming host_init() itself contains no backoff check:
    calling it directly always proceeds to attempt an open, regardless of
    _next_reconnect_time.
    """
    win = make_keyer(monkeypatch, tmp_path)
    win._next_reconnect_time = time.time() + 9999  # would block _attempt_reconnect()

    opened = []
    import keyer_mac.__main__ as mod

    class FakeSerial:
        is_open = True

        def __init__(self):
            opened.append(True)

        def open(self):
            pass

        def close(self):
            pass

        def write(self, data):
            pass

        def read(self, size=1):
            return b"WK\r"[:size]

    monkeypatch.setattr(mod.serial, "Serial", FakeSerial)

    win.host_init()  # default is_reconnect=False, explicit call

    assert opened  # open() was attempted despite _next_reconnect_time being far in the future


def test_reconnect_uses_longer_settle_than_first_open(monkeypatch, tmp_path):
    """host_open() sleeps longer before reading the version response on a
    reconnect (is_reconnect=True) than on a first/cold-boot open — the
    hypothesis being a reconnect may follow a mid-transaction error that
    leaves the device needing more time to settle (unverified against real
    hardware in this worktree; see deviation-log.md #8).
    """
    win = make_keyer(monkeypatch, tmp_path)

    class FakeSerial:
        is_open = True

        def open(self):
            pass

        def close(self):
            pass

        def write(self, data):
            pass

        def read(self, size=1):
            return b"WK\r"[:size]

    import keyer_mac.__main__ as mod

    monkeypatch.setattr(mod.serial, "Serial", lambda: FakeSerial())

    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    win.host_init(is_reconnect=False)
    first_open_settle = sleeps[-1]  # last sleep() call before the version read

    sleeps.clear()
    win.host_init(is_reconnect=True)
    reconnect_settle = sleeps[-1]

    assert first_open_settle == win._first_open_settle_s
    assert reconnect_settle == win._reconnect_settle_s
    assert reconnect_settle > first_open_settle
