"""Serial worker (masterplan Tech, module 4). Lives in its own QThread so the
UI thread never sleeps or waits on the keyer. Talks to the UI only through
signals.

Connect: try each candidate (ports.probe_order); the first that answers and
passes initialize() wins. Every connect re-sends every setting from the
worker's current values, never cached from an earlier connect.
Reconnect: a serial error, or an idle echo test with no answer, drops the
connection and an attempt follows at once; after a failed attempt the next
one is RETRY_S seconds later, every time. A newly plugged-in keyer is tried
immediately by the window's port watch, not after the wait.
"""

from __future__ import annotations

import logging
import time

import serial
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from keyer_mac import ports as ports_mod
from keyer_mac import winkeyer

log = logging.getLogger(__name__)

CLOSE_REOPEN_PAD_S = 0.3     # min gap between closing a port and opening one (deviation-log #9)
RETRY_S = 8                  # fixed wait between automatic attempts (no growing delays)
POLL_MS = 100
IDLE_ECHO_S = 10.0
RECENT_TRAFFIC_S = 2.0      # skip the idle echo test while the keyer is chatty


# Last port close in this process, shared by every Worker: (clock function, time).
# Per-instance memory missed the common case of a new window or worker opening
# right after the previous one closed (live: ~25% stalled handshakes at ~0 s gap,
# none at >= 0.3 s). A different clock function (tests) never matches.
_last_close: tuple = (None, 0.0)


class Worker(QObject):
    found = pyqtSignal(str, int, int)        # device, version byte, speed sent
    missing = pyqtSignal()
    disconnected = pyqtSignal()
    echoed = pyqtSignal(str)
    idle = pyqtSignal()                      # the keyer finished sending (busy -> idle)
    note = pyqtSignal(str)                   # text for the Message box
    diagnostic = pyqtSignal(str)             # why something failed (UI adds a time stamp)
    retry_scheduled = pyqtSignal(float)      # seconds until the next automatic attempt
    scan_requested = pyqtSignal(object, object, int, int)   # saved, manual, mode, speed

    def __init__(self, open_port=winkeyer.open_port, list_ports=ports_mod.list_ports,
                 clock=time.monotonic, sleep=time.sleep, schedule=None, auto_poll=True):
        super().__init__()
        self._open_port = open_port
        self._list_ports = list_ports
        self._clock = clock
        self._sleep = sleep
        self._schedule = schedule or self._qt_schedule
        self._auto_poll = auto_poll
        self._poll_timer: QTimer | None = None
        self._epoch = 0
        self._saved = self._manual = None
        self.mode_register = winkeyer.DEFAULT_MODE_REGISTER
        self.speed = winkeyer.DEFAULT_SPEED
        self.connected = False
        self.device: str | None = None
        self.port = None
        self.keyer: winkeyer.WinKeyer | None = None
        self._last_check = self._last_traffic = 0.0
        self.scan_requested.connect(self.scan)

    @staticmethod
    def _qt_schedule(delay_s: float, fn) -> None:
        QTimer.singleShot(int(delay_s * 1000), fn)

    # -- connect -----------------------------------------------------------
    @pyqtSlot(object, object, int, int)
    def scan(self, saved, manual, mode_register, speed):
        """Start (or restart) a scan with these settings."""
        self._saved, self._manual = saved, manual
        self.mode_register, self.speed = mode_register, speed
        self._epoch += 1
        if self.connected:
            self._close_port()
        self._attempt(self._epoch)

    def _attempt(self, epoch: int) -> None:
        if epoch != self._epoch or self.connected:
            return
        order = ports_mod.probe_order(self._list_ports(), self._saved, self._manual)
        if not order:
            self.diagnostic.emit("No WinKeyer-mini (USB 1a86:7523) is visible to the Mac")
        for device in order:
            port = None
            self._pad_after_close()
            try:
                port = self._open_port(device)
                keyer = winkeyer.WinKeyer(port, sleep=self._sleep, clock=self._clock)
                version = keyer.host_open()
                if version is None:
                    msg = f"{device} opened but the WinKeyer did not answer host open ({keyer.MAX_TRIES} tries)"
                    log.warning(msg)
                    self.diagnostic.emit(msg)
                elif keyer.initialize(self.mode_register, self.speed):
                    self._on_connected(device, port, keyer, version)
                    return
                else:
                    msg = f"{device} answered host open but failed the echo test after the settings"
                    log.warning(msg)
                    self.diagnostic.emit(msg)
            except (serial.SerialException, OSError) as exc:
                msg = winkeyer.describe_open_error(device, exc)
                log.warning(msg)
                self.diagnostic.emit(msg)
            if port is not None:
                try:
                    port.close()
                except (serial.SerialException, OSError):
                    pass
                self._mark_closed()
        self.missing.emit()
        self.retry_scheduled.emit(RETRY_S)
        self._schedule(RETRY_S, lambda e=epoch: self._attempt(e))

    def _mark_closed(self) -> None:
        global _last_close
        _last_close = (self._clock, self._clock())

    def _pad_after_close(self) -> None:
        """Opening a port right after closing one makes the WinKeyer miss the
        handshake (the close/reopen race); keep at least CLOSE_REOPEN_PAD_S."""
        clock_fn, closed_at = _last_close
        if clock_fn == self._clock:
            wait = CLOSE_REOPEN_PAD_S - (self._clock() - closed_at)
            if wait > 0:
                self._sleep(wait)

    def _on_connected(self, device, port, keyer, version) -> None:
        self.connected, self.device, self.port, self.keyer = True, device, port, keyer
        self._last_check = self._last_traffic = self._clock()
        self.found.emit(device, version, self.speed)
        if self._auto_poll:
            if self._poll_timer is None:
                self._poll_timer = QTimer(self)
                self._poll_timer.timeout.connect(self.poll)
            self._poll_timer.start(POLL_MS)

    # -- running -------------------------------------------------------------
    @pyqtSlot()
    def poll(self) -> None:
        if not self.connected:
            return
        try:
            text, went_idle = self.keyer.poll_with_status()
            now = self._clock()
            if text:
                self._last_traffic = now
                self.echoed.emit(text)
            if went_idle:
                self._last_traffic = now
                self.idle.emit()
            if (not text and not went_idle and now - self._last_check >= IDLE_ECHO_S
                    and now - self._last_traffic >= RECENT_TRAFFIC_S):
                self._last_check = now
                if not self.keyer.echo_test():
                    self._drop("no answer to the idle echo test")
        except (serial.SerialException, OSError) as exc:
            self._drop(f"serial error while reading: {exc}")

    def _close_port(self) -> None:
        if self._poll_timer:
            self._poll_timer.stop()
        for step in (lambda: self.keyer and self.keyer.host_close(),
                     lambda: self.port and self.port.close()):
            try:
                step()
            except (serial.SerialException, OSError):
                pass
        self.connected, self.port, self.keyer = False, None, None
        self._mark_closed()

    def _drop(self, reason: str = "unknown") -> None:
        self._close_port()
        self.diagnostic.emit(f"Keyer disconnected: {reason}")
        self._epoch += 1
        self.disconnected.emit()
        epoch = self._epoch
        self._schedule(0, lambda e=epoch: self._attempt(e))     # try again at once

    @pyqtSlot()
    def close(self) -> None:
        self._epoch += 1
        self._close_port()

    # -- commands (run on the worker thread) --------------------------------
    def _do(self, what: str, action) -> None:
        if not self.connected:
            self.note.emit(f"{what} dropped: keyer disconnected")
            return
        try:
            action(self.keyer)
        except (serial.SerialException, OSError) as exc:
            self._drop(f"write failed while sending ({what}): {exc}")

    @pyqtSlot(str)
    def send_text(self, text: str) -> None:
        self._do("send", lambda k: k.send_text(text))

    @pyqtSlot(str)
    def send_blended(self, text: str) -> None:
        self._do("sendblended", lambda k: k.send_blended(text))

    @pyqtSlot()
    def backspace(self) -> None:
        self._do("backspace", lambda k: k.backspace())

    @pyqtSlot()
    def tune_on(self) -> None:
        self._do("tuneon", lambda k: k.tune_on())

    @pyqtSlot()
    def tune_off(self) -> None:
        self._do("tuneoff", lambda k: k.tune_off())

    @pyqtSlot()
    def clear_buffer(self) -> None:
        self._do("clearbuffer", lambda k: k.clear_buffer())

    @pyqtSlot(int)
    def set_speed(self, wpm: int) -> None:
        """Remember the speed for the next connect; send it now if connected."""
        self.speed = wpm
        if self.connected:
            self._do("setspeed", lambda k: k.set_speed(wpm))

    @pyqtSlot(int)
    def set_mode(self, register: int) -> None:
        self.mode_register = register
        if self.connected:
            self._do("setmode", lambda k: k.set_mode(register))
