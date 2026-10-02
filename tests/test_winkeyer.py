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
