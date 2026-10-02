"""WinKeyer host protocol (masterplan Tech, module 3). Protocol only: no Qt,
no threads. Works on any serial-like object (`write`, `read`, `reset_input_buffer`),
so unit tests use a fake and tools/ use the real port.

Byte sequences are those proven live in tools/winkeyer_diagnostic.py (host
open/close) and ported from pywinkeyerserial (mode, speed). The echo test
(admin 0x04) is UNVERIFIED until Task 2.2's live run proves it (rule 9).
"""

from __future__ import annotations

import time

HOST_CLOSE = bytes([0x00, 0x03])
HOST_OPEN = bytes([0x00, 0x02])
ECHO_TEST = 0x04            # admin: 00 04 <byte> -> <byte>
CMD_SET_SPEED = 0x02
CMD_SET_MODE = 0x0E

SPEED_MIN, SPEED_MAX = 6, 34            # UI dropdown: even values only
DEFAULT_SPEED = 20
DEFAULT_MODE_REGISTER = 0b11001110

SERIAL_SETTINGS = dict(baudrate=1200, bytesize=8, parity="N", stopbits=2, dsrdtr=True)


def open_port(device: str, timeout: float = 0.05):
    """Open `device` with the WinKeyer's serial settings (1200 8N2, DTR on)."""
    import serial

    port = serial.Serial()
    port.port = device
    for key, value in SERIAL_SETTINGS.items():
        setattr(port, key, value)
    port.rtscts = False
    port.timeout = timeout
    port.write_timeout = 1
    port.open()
    return port


class WinKeyer:
    """One WinKeyer session on an already-open port.

    `sleep` and `clock` are injectable so tests run instantly.
    """

    RESET_WAIT_S = 1.0       # after host close, before host open (keyer reset)
    RETRY_GAP_S = 0.3
    MAX_TRIES = 3
    REPLY_TIMEOUT_S = 0.5

    def __init__(self, port, sleep=time.sleep, clock=time.monotonic):
        self.port = port
        self._sleep = sleep
        self._clock = clock
        self.version: int | None = None

    # -- low level -------------------------------------------------------
    def _write(self, data: bytes) -> None:
        self.port.write(data)

    def _read(self, n: int, timeout: float | None = None) -> bytes:
        """Read exactly `n` bytes, or whatever arrived before the timeout."""
        deadline = self._clock() + (self.REPLY_TIMEOUT_S if timeout is None else timeout)
        buf = b""
        while len(buf) < n and self._clock() < deadline:
            chunk = self.port.read(n - len(buf))
            if chunk:
                buf += chunk
            else:
                self._sleep(0.01)
        return buf

    # -- session ---------------------------------------------------------
    def host_open(self) -> int | None:
        """Close, wait for the keyer reset, open; return the version byte.

        Up to MAX_TRIES tries, RETRY_GAP_S apart, on the already-open port
        (the port itself is never reopened per try). None if no reply.
        """
        for attempt in range(self.MAX_TRIES):
            self._write(HOST_CLOSE)
            self._sleep(self.RESET_WAIT_S)
            self.port.reset_input_buffer()
            self._write(HOST_OPEN)
            reply = self._read(1)
            if len(reply) == 1:
                self.version = reply[0]
                return self.version
            if attempt + 1 < self.MAX_TRIES:
                self._sleep(self.RETRY_GAP_S)
        self.version = None
        return None

    def host_close(self) -> None:
        self._write(HOST_CLOSE)

    def echo_test(self, value: int = 0x55) -> bool:
        """Admin echo: the keyer must answer with the byte sent."""
        self.port.reset_input_buffer()
        self._write(bytes([0x00, ECHO_TEST, value]))
        return self._read(1) == bytes([value])

    # -- settings --------------------------------------------------------
    def set_mode(self, register: int) -> None:
        self._write(bytes([CMD_SET_MODE, register & 0xFF]))

    def set_speed(self, wpm: int) -> None:
        if not SPEED_MIN <= wpm <= SPEED_MAX:
            raise ValueError(f"speed {wpm} outside {SPEED_MIN}-{SPEED_MAX}")
        self._write(bytes([CMD_SET_SPEED, wpm]))

    def send_text(self, text: str) -> None:
        self._write(text.upper().encode("ascii", "ignore"))
