"""Logic-only tests confirming the WK-mini's phantom pot line is fully
ignored (deviation-log.md #10, superseding #6's arbitration approach now
that the operator has confirmed this hardware has no physical pot).
Replaces test_speed_arbitration.py, whose potspeed()-based tests no
longer apply — potspeed() has been removed; pot-status bytes are now
discarded directly in getwaiting()'s dispatch. No hardware needed.
"""

import time


class DummyPort:
    """Scripts a single pot-status byte for getwaiting() to poll, same
    shape as test_reconnect_backoff.py's DummyPort."""

    def __init__(self, read_bytes=b"", in_waiting=0):
        self._read_bytes = read_bytes
        self.in_waiting = in_waiting
        self.is_open = True

    def write(self, data):
        pass

    def read(self, size=1):
        data, self._read_bytes = self._read_bytes[:size], self._read_bytes[size:]
        return data


def test_default_speed_is_20_wpm(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "config.json"))
    from keyer_mac.__main__ import WinKeyer

    win = WinKeyer()
    assert win.spinBox_speed.value() == 20


def test_potspeed_no_longer_exists(monkeypatch, tmp_path):
    """Documents the intentional removal, not just its absence — a
    future reader shouldn't wonder if it was lost by accident."""
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "config.json"))
    from keyer_mac.__main__ import WinKeyer

    win = WinKeyer()
    assert not hasattr(win, "potspeed")


def test_pot_status_byte_ignored_via_getwaiting(monkeypatch, tmp_path):
    """A pot-status byte (top 2 bits '10') arriving through getwaiting()'s
    dispatch — 158 & 0xC0 == 0x80, decodes to 35 WPM, the operator's
    actual observed phantom reading — must never change the spinbox."""
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "config.json"))
    from keyer_mac.__main__ import WinKeyer

    win = WinKeyer()
    assert win.spinBox_speed.value() == 20

    win.port = DummyPort(read_bytes=bytes([158]), in_waiting=1)
    win.last_tx_time = time.time()
    win.getwaiting()

    assert win.spinBox_speed.value() == 20


def test_manual_spinbox_change_still_works(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "config.json"))
    from keyer_mac.__main__ import WinKeyer

    win = WinKeyer()
    win.port = DummyPort()

    win.spinBox_speed.setValue(25)
    assert win.spinBox_speed.value() == 25
    assert win._last_manual_speed == 25
