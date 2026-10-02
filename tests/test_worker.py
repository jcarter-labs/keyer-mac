"""Masterplan 3.4: scan, found, missing, disconnect, reconnect with backoff,
settings re-sent in order on every connect, echo/status filtering, and 50
simulated unplug/replug cycles. Fake serial only; no Qt thread needed
(the worker's slots are called directly, timers are injected)."""

from collections import namedtuple

import pytest
import serial

from keyer_mac import winkeyer
from keyer_mac.worker import Backoff, Worker

P = namedtuple("P", "device vid pid")
WK = P("/dev/cu.usbserial-SIM", 0x1A86, 0x7523)

PINNED = [bytes([c, *p]) for c, p in winkeyer.PINNED_PARAMETERS]


class World:
    """A simulated keyer that can be unplugged and replugged."""

    def __init__(self):
        self.plugged = True
        self.ports = []        # every FakePort ever opened
        self.hung = False      # answers nothing (a silent hang)

    def list_ports(self):
        return [WK] if self.plugged else []

    def open_port(self, device):
        if not self.plugged:
            raise serial.SerialException("could not open port: no such device")
        port = FakePort(self)
        self.ports.append(port)
        return port

    def unplug(self):
        self.plugged = False

    def plug(self):
        self.plugged = True


class FakePort:
    def __init__(self, world):
        self.world, self.written, self._inbox, self.closed = world, [], b"", False

    def _check(self):
        if not self.world.plugged:
            raise serial.SerialException("device disconnected")

    def write(self, data):
        self._check()
        data = bytes(data)
        self.written.append(data)
        if self.world.hung:
            return
        if data == b"\x00\x02":
            self._inbox += b"\x1f"
        elif data[:2] == b"\x00\x04":
            self._inbox += data[2:3]

    def read(self, n):
        self._check()
        out, self._inbox = self._inbox[:n], self._inbox[n:]
        return out

    def reset_input_buffer(self):
        self._inbox = b""

    def close(self):
        self.closed = True


class Harness:
    def __init__(self):
        self.world = World()
        self.t = 0.0
        self.scheduled = []     # (delay, fn)
        self.events = []        # (signal name, args)
        self.worker = Worker(open_port=self.world.open_port, list_ports=self.world.list_ports,
                             clock=self.clock, sleep=self.sleep,
                             schedule=lambda d, fn: self.scheduled.append((d, fn)), auto_poll=False)
        for name in ("found", "missing", "disconnected", "echoed", "note", "retry_scheduled"):
            getattr(self.worker, name).connect(lambda *a, n=name: self.events.append((n, a)))

    def clock(self):
        self.t += 0.001
        return self.t

    def sleep(self, s):
        self.t += s

    def names(self):
        return [e[0] for e in self.events]

    def fire_next_retry(self):
        delay, fn = self.scheduled.pop(0)
        fn()
        return delay


@pytest.fixture
def h():
    return Harness()


def test_scan_finds_the_keyer_and_sends_every_setting_in_order(h):
    h.worker.scan(None, None, 0b11001110, 20)
    assert h.names() == ["found"]
    assert h.events[0][1] == (WK.device, 0x1F, 20)
    assert h.world.ports[0].written == [
        b"\x00\x03", b"\x00\x02", b"\x0e\xce", b"\x02\x14", *PINNED, b"\x00\x04\x55"]


def test_missing_then_backoff_1_2_4_8_16_30_30(h):
    h.world.unplug()
    h.worker.scan(None, None, 0b11001110, 20)
    delays = [h.events[-1][1][0]]
    for _ in range(6):
        h.fire_next_retry()
        delays.append(h.events[-1][1][0])
    assert delays == [1, 2, 4, 8, 16, 30, 30]
    assert h.names().count("missing") == 7
    assert "found" not in h.names()


def test_retry_finds_the_keyer_once_plugged_and_resets_backoff(h):
    h.world.unplug()
    h.worker.scan(None, None, 0b11001110, 20)
    h.fire_next_retry(); h.fire_next_retry()       # two more misses: next delay is 4
    h.world.plug()
    h.fire_next_retry()
    assert h.names()[-1] == "found"
    assert h.worker.connected
    assert h.worker._backoff.failures == 0


def test_serial_error_drops_and_schedules_a_reconnect_in_1_s(h):
    h.worker.scan(None, None, 0b11001110, 20)
    h.world.unplug()
    h.worker.poll()
    assert h.names()[-2:] == ["disconnected", "retry_scheduled"]
    assert h.events[-1][1] == (1,)
    assert not h.worker.connected
    assert h.world.ports[0].closed


def test_settings_are_resent_from_current_values_on_every_connect(h):
    h.worker.scan(None, None, 0b11001110, 20)
    h.worker.set_speed(30)                  # changed while connected
    h.world.unplug(); h.worker.poll()       # drop
    h.worker.set_speed(24)                  # changed while disconnected: remembered, not sent
    h.world.plug(); h.fire_next_retry()
    second = h.world.ports[-1].written
    assert second[:4] == [b"\x00\x03", b"\x00\x02", b"\x0e\xce", b"\x02\x18"]
    assert b"\x02\x1e" in h.world.ports[0].written        # 30 was sent live


def test_echo_text_is_emitted_and_status_bytes_are_dropped(h):
    h.worker.scan(None, None, 0b11001110, 20)
    h.world.ports[0]._inbox = b"\xc4TE\xc0ST"
    h.worker.poll()
    assert ("echoed", ("TEST",)) in h.events


def test_idle_echo_failure_drops_the_connection(h):
    h.worker.scan(None, None, 0b11001110, 20)
    h.world.hung = True
    h.t += 20                               # past the 10 s idle interval
    h.worker.poll()
    assert "disconnected" in h.names()


def test_idle_echo_test_does_not_run_while_the_keyer_is_chatty(h):
    h.worker.scan(None, None, 0b11001110, 20)
    h.world.hung = True
    h.t += 20
    h.worker._last_traffic = h.t            # traffic just now
    h.worker.poll()
    assert "disconnected" not in h.names()


def test_commands_while_disconnected_are_dropped_with_a_note(h):
    h.world.unplug()
    h.worker.scan(None, None, 0b11001110, 20)
    h.worker.send_text("CQ")
    assert ("note", ("send dropped: keyer disconnected",)) in h.events


def test_a_write_error_while_sending_drops_the_connection(h):
    h.worker.scan(None, None, 0b11001110, 20)
    h.world.unplug()
    h.worker.send_text("CQ")
    assert "disconnected" in h.names()


def test_backoff_sequence_and_reset():
    b = Backoff()
    assert [b.next() for _ in range(8)] == [1, 2, 4, 8, 16, 30, 30, 30]
    b.reset()
    assert b.next() == 1


def test_manual_scan_restart_cancels_the_pending_retry(h):
    h.world.unplug()
    h.worker.scan(None, None, 0b11001110, 20)
    stale = h.scheduled[0][1]
    h.world.plug()
    h.worker.scan(None, None, 0b11001110, 20)       # user re-picks the port
    assert h.worker.connected
    count = h.names().count("found")
    stale()                                          # the old timer fires: ignored
    assert h.names().count("found") == count


def test_50_simulated_unplug_replug_cycles_all_reconnect_with_fresh_settings(h):
    speeds = [6 + 2 * (i % 15) for i in range(50)]
    h.worker.scan(None, None, 0b11001110, 20)
    assert h.names() == ["found"]
    failures = 0
    for i, speed in enumerate(speeds):
        h.worker.set_speed(speed)
        h.world.unplug()
        h.worker.poll()                              # error detected -> disconnected
        for _ in range(i % 4):                       # a few failed retries first
            h.fire_next_retry()
        h.world.plug()
        h.fire_next_retry()                          # succeeds
        port = h.world.ports[-1]
        expected = [b"\x00\x03", b"\x00\x02", b"\x0e\xce", bytes([2, speed]), *PINNED, b"\x00\x04\x55"]
        failures += (not h.worker.connected) or port.written != expected
        h.scheduled.clear()
    assert failures == 0
    assert h.names().count("found") == 51
    assert h.names().count("disconnected") == 50
