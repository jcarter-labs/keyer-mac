"""Masterplan 3.3: exact bytes and retry behaviour on a fake serial port."""

import pytest

from keyer_mac.winkeyer import WinKeyer


class FakePort:
    """Serial-like fake. `replies` maps a written byte string to the bytes to
    queue when it is written; everything written is logged."""

    def __init__(self, replies=None):
        self.written = []
        self.replies = replies or {}
        self._inbox = b""

    def write(self, data):
        self.written.append(bytes(data))
        self._inbox += self.replies.get(bytes(data), b"")

    def read(self, n):
        out, self._inbox = self._inbox[:n], self._inbox[n:]
        return out

    def reset_input_buffer(self):
        self._inbox = b""


class Clock:
    """Deterministic time: sleep advances the clock; every read poll costs 1 ms."""

    def __init__(self):
        self.t = 0.0

    def sleep(self, s):
        self.t += s

    def now(self):
        self.t += 0.001
        return self.t


def make(replies=None):
    clock = Clock()
    port = FakePort(replies)
    return WinKeyer(port, sleep=clock.sleep, clock=clock.now), port, clock


def test_host_open_sends_close_then_open_and_returns_version():
    wk, port, _ = make({b"\x00\x02": b"\x1f"})
    assert wk.host_open() == 0x1F
    assert port.written == [b"\x00\x03", b"\x00\x02"]


def test_host_open_retries_three_times_then_gives_up():
    wk, port, clock = make()
    assert wk.host_open() is None
    assert port.written == [b"\x00\x03", b"\x00\x02"] * 3
    assert wk.version is None
    # 3 x (1.0 s reset wait + 0.5 s reply timeout) + 2 x 0.3 s gap
    assert 4.5 + 0.6 <= clock.t <= 5.5


def test_host_open_recovers_on_second_try():
    wk, port, _ = make()
    answers = iter([b"", b"\x1f"])
    orig = port.write

    def write(data):
        orig(data)
        if bytes(data) == b"\x00\x02":
            port._inbox += next(answers)

    port.write = write
    assert wk.host_open() == 0x1F
    assert port.written.count(b"\x00\x02") == 2


def test_echo_test_passes_only_on_the_same_byte():
    wk, port, _ = make({b"\x00\x04\x55": b"\x55"})
    assert wk.echo_test(0x55) is True
    assert port.written[-1] == b"\x00\x04\x55"
    wk2, _, _ = make({b"\x00\x04\x55": b"\x56"})
    assert wk2.echo_test(0x55) is False
    wk3, _, _ = make()
    assert wk3.echo_test(0x55) is False


def test_mode_and_speed_bytes():
    wk, port, _ = make()
    wk.set_mode(0b11001110)
    wk.set_speed(20)
    assert port.written == [b"\x0e\xce", b"\x02\x14"]


@pytest.mark.parametrize("bad", [5, 35, 0, 100, -1])
def test_speed_outside_6_to_34_is_rejected_and_nothing_is_sent(bad):
    wk, port, _ = make()
    with pytest.raises(ValueError):
        wk.set_speed(bad)
    assert port.written == []


def test_send_text_uppercases():
    wk, port, _ = make()
    wk.send_text("cq test")
    assert port.written == [b"CQ TEST"]


def test_initialize_sends_mode_potset_speed_then_every_pinned_parameter_then_echo():
    wk, port, _ = make({b"\x00\x04\x55": b"\x55"})
    assert wk.initialize(0b11001110, 20) is True
    assert port.written == [
        b"\x0e\xce", b"\x05\x05\x32\x00", b"\x02\x14",
        b"\x03\x32", b"\x17\x32", b"\x10\x00", b"\x11\x00",
        b"\x12\x32", b"\x0d\x00", b"\x04\x00\x00",
        b"\x00\x04\x55",
    ]


def test_initialize_fails_when_the_echo_test_does_not_answer():
    wk, _, _ = make()
    assert wk.initialize() is False


def test_sidetone_and_pin_config_are_never_written():
    from keyer_mac.winkeyer import PINNED_PARAMETERS
    assert {c for c, _ in PINNED_PARAMETERS}.isdisjoint({0x01, 0x09})


def test_speed_pot_setup_precedes_the_speed_command():
    """Without 05 05 32 00 the live keyer ignored speeds above ~15 WPM (measured
    by echo timing), so it must come before the speed write, every time."""
    from keyer_mac.winkeyer import POTSET
    assert POTSET == bytes([0x05, 0x05, 0x32, 0x00])
    wk, port, _ = make({b"\x00\x04\x55": b"\x55"})
    wk.initialize(0b11001110, 34)
    assert port.written.index(POTSET) < port.written.index(b"\x02\x22")
