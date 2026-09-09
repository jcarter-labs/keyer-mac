"""Logic-only tests for speed-control arbitration between the spinbox and
the pot line (deviation-log.md #6). No hardware needed: a dummy port with
a no-op write() lets setspeed()'s hasattr(self.port, "write") gate pass,
same as a real connected device, without touching a real serial port.
"""


class DummyPort:
    def write(self, data):
        pass


def test_stale_pot_echo_does_not_override_manual_speed(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "config.json"))
    from keyer_mac.__main__ import WinKeyer

    win = WinKeyer()
    win.port = DummyPort()

    win.potspeed(158)  # 158 - 123 = 35, the initial/only pot reading
    assert win.spinBox_speed.value() == 35

    win.spinBox_speed.setValue(20)  # user takes manual control
    assert win.spinBox_speed.value() == 20

    win.potspeed(158)  # same stale reading repeats — must NOT reclobber
    assert win.spinBox_speed.value() == 20


def test_genuine_pot_change_still_takes_control(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "config.json"))
    from keyer_mac.__main__ import WinKeyer

    win = WinKeyer()
    win.port = DummyPort()

    win.potspeed(158)  # 35 WPM
    win.spinBox_speed.setValue(20)  # manual override
    assert win.spinBox_speed.value() == 20

    win.potspeed(143)  # 143 - 123 = 20: a real, different pot reading
    assert win.spinBox_speed.value() == 20


def test_repeated_manual_value_does_not_resend(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "config.json"))
    from keyer_mac.__main__ import WinKeyer

    win = WinKeyer()
    win.port = DummyPort()

    win.spinBox_speed.setValue(25)
    win._last_pot_speed = 999  # simulate a distinct prior pot reading
    win.spinBox_speed.setValue(25)  # no actual change — Qt won't even signal
    assert win.spinBox_speed.value() == 25
    assert win._last_pot_speed == 999  # unaffected either way
