"""Serial worker (masterplan Tech, module 4). Lives in its own QThread so the
UI thread never sleeps or waits on the keyer. Talks to the UI only through
signals.

Connect: try each candidate (ports.probe_order); the first that answers and
passes initialize() wins. Every connect re-sends every setting from the
worker's current values, never cached from an earlier connect.
Reconnect: a serial error, or an idle echo test with no answer, drops the
connection; retries then back off 1, 2, 4, 8, 16, 30, 30 ... s.
"""

from __future__ import annotations

import time

import serial
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from keyer_mac import ports as ports_mod
from keyer_mac import winkeyer

POLL_MS = 100
IDLE_ECHO_S = 10.0
RECENT_TRAFFIC_S = 2.0      # skip the idle echo test while the keyer is chatty


class Backoff:
    DELAYS = (1, 2, 4, 8, 16, 30)

    def __init__(self):
        self.failures = 0

    def next(self) -> int:
        delay = self.DELAYS[min(self.failures, len(self.DELAYS) - 1)]
        self.failures += 1
        return delay

    def reset(self) -> None:
        self.failures = 0


class Worker(QObject):
    found = pyqtSignal(str, int, int)        # device, version byte, speed sent
    missing = pyqtSignal()
    disconnected = pyqtSignal()
    echoed = pyqtSignal(str)
    note = pyqtSignal(str)                   # text for the Message box
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
        self._backoff = Backoff()
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
        self._backoff.reset()
        if self.connected:
            self._close_port()
        self._attempt(self._epoch)

    def _attempt(self, epoch: int) -> None:
        if epoch != self._epoch or self.connected:
            return
        for device in ports_mod.probe_order(self._list_ports(), self._saved, self._manual):
            port = None
            try:
                port = self._open_port(device)
                keyer = winkeyer.WinKeyer(port, sleep=self._sleep, clock=self._clock)
                version = keyer.host_open()
                if version is not None and keyer.initialize(self.mode_register, self.speed):
                    self._on_connected(device, port, keyer, version)
                    return
            except (serial.SerialException, OSError):
                pass            # a bad port just means try the next
            if port is not None:
                try:
                    port.close()
                except (serial.SerialException, OSError):
                    pass
        self.missing.emit()
        delay = self._backoff.next()
        self.retry_scheduled.emit(delay)
        self._schedule(delay, lambda e=epoch: self._attempt(e))

    def _on_connected(self, device, port, keyer, version) -> None:
        self._backoff.reset()
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
            text = self.keyer.poll()
            now = self._clock()
            if text:
                self._last_traffic = now
                self.echoed.emit(text)
            elif (now - self._last_check >= IDLE_ECHO_S
                  and now - self._last_traffic >= RECENT_TRAFFIC_S):
                self._last_check = now
                if not self.keyer.echo_test():
                    self._drop()
        except (serial.SerialException, OSError):
            self._drop()

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

    def _drop(self) -> None:
        self._close_port()
        self._epoch += 1
        self._backoff.reset()
        self.disconnected.emit()
        epoch = self._epoch
        delay = self._backoff.next()
        self.retry_scheduled.emit(delay)
        self._schedule(delay, lambda e=epoch: self._attempt(e))

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
        except (serial.SerialException, OSError):
            self._drop()

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
