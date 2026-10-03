"""Masterplan 3.4: scan, found, missing, disconnect, reconnect every 8 s,
settings re-sent in order on every connect, echo/status filtering, and 50
simulated unplug/replug cycles. Fake serial only; no Qt thread needed
(the worker's slots are called directly, timers are injected)."""

from collections import namedtuple

import pytest
import serial

from keyer_mac import winkeyer
from keyer_mac.worker import RETRY_S, Worker

P = namedtuple("P", "device vid pid")
WK = P("/dev/cu.usbserial-SIM", 0x1A86, 0x7523)

PINNED = [bytes([c, *p]) for c, p in winkeyer.PINNED_PARAMETERS]
POTSET = winkeyer.POTSET


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
        for name in ("found", "missing", "disconnected", "echoed", "note", "retry_scheduled", "diagnostic"):
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
        b"\x00\x03", b"\x00\x02", b"\x0e\xce", POTSET, b"\x02\x14", *PINNED, b"\x00\x04\x55"]


def test_missing_retries_every_8_s_forever_with_no_growing_delay(h):
    h.world.unplug()
    h.worker.scan(None, None, 0b11001110, 20)
    delays = [h.events[-1][1][0]]
    for _ in range(9):
        h.fire_next_retry()
        delays.append(h.events[-1][1][0])
    assert delays == [8] * 10 and RETRY_S == 8
    assert h.names().count("missing") == 10
    assert "found" not in h.names()


def test_retry_finds_the_keyer_once_plugged(h):
    h.world.unplug()
    h.worker.scan(None, None, 0b11001110, 20)
    h.fire_next_retry(); h.fire_next_retry()       # two more misses
    h.world.plug()
    h.fire_next_retry()
    assert h.names()[-1] == "found"
    assert h.worker.connected


def test_serial_error_drops_and_tries_again_at_once(h):
    h.worker.scan(None, None, 0b11001110, 20)
    h.world.unplug()
    h.worker.poll()
    assert h.names()[-1] == "disconnected"
    assert h.scheduled[0][0] == 0            # an immediate attempt, not a wait
    assert not h.worker.connected
    assert h.world.ports[0].closed


def test_settings_are_resent_from_current_values_on_every_connect(h):
    h.worker.scan(None, None, 0b11001110, 20)
    h.worker.set_speed(30)                  # changed while connected
    h.world.unplug(); h.worker.poll()       # drop
    h.worker.set_speed(24)                  # changed while disconnected: remembered, not sent
    h.world.plug(); h.fire_next_retry()
    second = h.world.ports[-1].written
    assert second[:5] == [b"\x00\x03", b"\x00\x02", b"\x0e\xce", POTSET, b"\x02\x18"]
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
        expected = [b"\x00\x03", b"\x00\x02", b"\x0e\xce", POTSET, bytes([2, speed]), *PINNED, b"\x00\x04\x55"]
        failures += (not h.worker.connected) or port.written != expected
        h.scheduled.clear()
    assert failures == 0
    assert h.names().count("found") == 51
    assert h.names().count("disconnected") == 50


def test_reopen_waits_out_the_0_3_s_close_reopen_pad(h):
    h.worker.scan(None, None, 0b11001110, 20)
    opened_at = []
    real_open = h.worker._open_port
    h.worker._open_port = lambda d: (opened_at.append(h.t), real_open(d))[1]
    h.worker._close_port()
    closed_at = h.t
    h.worker._attempt(h.worker._epoch)
    assert opened_at and opened_at[0] - closed_at >= 0.3 - 1e-6


def test_first_open_has_no_pad(h):
    t0 = h.t
    h.worker.scan(None, None, 0b11001110, 20)
    # only the protocol's own 1.0 s reset wait advances the clock, no extra pad
    assert h.t - t0 < 1.1


def test_pad_is_shared_across_worker_instances(h):
    """A second Worker (new window) opening right after the first closed must
    still wait out the pad: the stall seen live came from exactly that."""
    h.worker.scan(None, None, 0b11001110, 20)
    h.worker._close_port()
    closed_at = h.t
    other = Worker(open_port=h.world.open_port, list_ports=h.world.list_ports,
                   clock=h.clock, sleep=h.sleep, schedule=lambda d, fn: None, auto_poll=False)
    opened_at = []
    real_open = other._open_port
    other._open_port = lambda d: (opened_at.append(h.t), real_open(d))[1]
    other.scan(None, None, 0b11001110, 20)
    assert opened_at[0] - closed_at >= 0.3 - 1e-6


# ---- diagnostics: every failure says why (printed in the Message box) -------------

def diag(h):
    return [e[1][0] for e in h.events if e[0] == "diagnostic"]


def test_no_keyer_visible_is_explained(h):
    h.world.unplug()
    h.worker.scan(None, None, 0b11001110, 20)
    assert diag(h) == ["No WinKeyer-mini (USB 1a86:7523) is visible to the Mac"]


def test_a_port_that_will_not_open_is_explained_with_the_error(h):
    h.world.open_port_orig = h.world.open_port
    def refuse(device):
        raise serial.SerialException("permission denied")
    h.worker._open_port = refuse
    h.worker.scan(None, None, 0b11001110, 20)
    assert diag(h) == [f"{WK.device} could not be used: permission denied"]


def test_a_port_held_by_another_program_says_so_plainly(h):
    def refuse(device):
        raise serial.SerialException(f"Could not exclusively lock port {device}: [Errno 35] Resource temporarily unavailable")
    h.worker._open_port = refuse
    h.worker.scan(None, None, 0b11001110, 20)
    assert diag(h) == [f"{WK.device} is in use by another program (another keyer-mac window?). "
                       "Close it; this window will connect by itself"]


def test_a_keyer_that_does_not_answer_is_explained(h):
    h.world.hung = True
    h.worker.scan(None, None, 0b11001110, 20)
    assert diag(h) == [f"{WK.device} opened but the WinKeyer did not answer host open (3 tries)"]


def test_a_failed_echo_test_after_settings_is_explained(h):
    real = winkeyer.WinKeyer.echo_test
    winkeyer.WinKeyer.echo_test = lambda self, value=0x55: False
    try:
        h.worker.scan(None, None, 0b11001110, 20)
    finally:
        winkeyer.WinKeyer.echo_test = real
    assert diag(h) == [f"{WK.device} answered host open but failed the echo test after the settings"]


def test_a_dropped_connection_says_why(h):
    h.worker.scan(None, None, 0b11001110, 20)
    h.world.unplug()
    h.worker.poll()
    assert any(d.startswith("Keyer disconnected: serial error while reading") for d in diag(h))


def test_an_idle_echo_failure_says_why(h):
    h.worker.scan(None, None, 0b11001110, 20)
    h.world.hung = True
    h.t += 20
    h.worker.poll()
    assert "Keyer disconnected: no answer to the idle echo test" in diag(h)


def test_a_write_error_names_the_command(h):
    h.worker.scan(None, None, 0b11001110, 20)
    h.world.unplug()
    h.worker.send_text("CQ")
    assert any("write failed while sending (send)" in d for d in diag(h))


def test_a_good_connect_prints_no_diagnostics(h):
    h.worker.scan(None, None, 0b11001110, 20)
    assert diag(h) == []


def test_idle_signal_fires_once_when_the_keyer_goes_busy_to_idle(h):
    idles = []
    h.worker.idle.connect(lambda: idles.append(1))
    h.worker.scan(None, None, 0b11001110, 20)
    h.world.ports[0]._inbox = b"\xc4E\xc0"
    h.worker.poll()
    assert idles == [1] and ("echoed", ("E",)) in h.events
    h.world.ports[0]._inbox = b"\xc0"
    h.worker.poll()
    assert idles == [1]
