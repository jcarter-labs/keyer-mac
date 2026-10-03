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

# Parameters the app does not expose, pinned on every connect (Data sources step 3.3).
# (command, parameter bytes). UNVERIFIED: values are the K1EL documented defaults as
# remembered; the WK-mini cannot report them back (Task 2.3), so the only check is
# that the writes are accepted and the echo test still answers. Sidetone (01) and
# pin configuration (09) are deliberately NOT touched: they are wiring-specific and
# a wrong pin value could disable keying.
PINNED_PARAMETERS = (
    (0x03, (50,)),       # weighting 50
    (0x17, (50,)),       # dit/dah ratio 50 (3:1)
    (0x10, (0,)),        # first extension 0
    (0x11, (0,)),        # key compensation 0
    (0x12, (50,)),       # paddle switchpoint 50
    (0x0D, (0,)),        # Farnsworth off
    (0x04, (0, 0)),      # PTT lead-in 0, tail 0
)

# Setup Speed Pot: minimum 5 WPM, range 50 (5-55 WPM), as 1.0 sent on every connect.
# The WK-mini has no pot, but this command also sets the speed range the keyer
# accepts from the host: WITHOUT it, speed commands above ~15 WPM were ignored
# (live, 2026-10-02: set 20 and 34 both measured 15 WPM; with it, 4/4 followed).
POTSET = bytes([0x05, 0x05, 0x32, 0x00])

SPEED_MIN, SPEED_MAX = 6, 34            # UI dropdown: even values only
DEFAULT_SPEED = 20
DEFAULT_MODE_REGISTER = 0b11001110

SERIAL_SETTINGS = dict(baudrate=1200, bytesize=8, parity="N", stopbits=2, dsrdtr=True)


def format_version(version: int) -> str:
    """Version byte 0x1f (31) -> "3.1"."""
    return f"{version // 10}.{version % 10}"


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
        self._busy = False

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
        """Admin echo: the keyer must answer with the byte sent. Status bytes
        (0xc0-0xff) that arrive around the reply are skipped."""
        self.port.reset_input_buffer()
        self._write(bytes([0x00, ECHO_TEST, value]))
        deadline = self._clock() + self.REPLY_TIMEOUT_S
        while self._clock() < deadline:
            chunk = self.port.read(1)
            if not chunk:
                self._sleep(0.01)
                continue
            if chunk[0] >= 0xC0:
                continue
            return chunk[0] == value
        return False

    def initialize(self, mode_register: int = DEFAULT_MODE_REGISTER, speed: int = DEFAULT_SPEED) -> bool:
        """After a successful host_open: send every setting, then verify.

        Order (Data sources, step 3): mode register, speed-pot setup, speed,
        then the pinned parameters, then the echo test. The keyer cannot report
        its speed back, but the effect is measurable: the echo timing of sent
        characters (tools/live_speed_diagnostic.py).
        """
        self.set_mode(mode_register)
        self._write(POTSET)
        self.set_speed(speed)
        for command, params in PINNED_PARAMETERS:
            self._write(bytes([command, *params]))
        return self.echo_test()

    # -- settings --------------------------------------------------------
    def set_mode(self, register: int) -> None:
        self._write(bytes([CMD_SET_MODE, register & 0xFF]))

    def set_speed(self, wpm: int) -> None:
        if not SPEED_MIN <= wpm <= SPEED_MAX:
            raise ValueError(f"speed {wpm} outside {SPEED_MIN}-{SPEED_MAX}")
        self._write(bytes([CMD_SET_SPEED, wpm]))

    def send_text(self, text: str) -> None:
        """Send printable ASCII only. Bytes below 0x20 are keyer COMMANDS (0x0A is
        Clear Buffer, 0x0D is Farnsworth and swallows the next byte), so they are
        never passed through as text (live probe, 2026-10-02)."""
        data = bytes(b for b in text.upper().encode("ascii", "ignore") if 0x20 <= b < 0x7F)
        if data:
            self._write(data)

    # -- sending and status ------------------------------------------------
    def send_blended(self, text: str) -> None:
        """Glue characters into a prosign."""
        self._write(b"\x1b" + text.upper().encode("ascii", "ignore"))

    def backspace(self) -> None:
        """Erase the last character from the keyer's buffer if not yet sent."""
        self._write(b"\x08")

    def tune_on(self) -> None:
        self._write(b"\x0b\x01")

    def tune_off(self) -> None:
        self._write(b"\x0b\x00")

    def clear_buffer(self) -> None:
        self._write(b"\x0a")

    def poll(self) -> str:
        """Read whatever the keyer has sent. Returns the echoed characters;
        status bytes (0xc0-0xff) and other control bytes are dropped."""
        return self.poll_with_status()[0]

    def poll_with_status(self) -> tuple[str, bool]:
        """(echoed characters, went_idle). A status byte 0xc0-0xff carries the
        BUSY flag in bit 2; went_idle is True when busy changed to idle."""
        data = self.port.read(64)
        went_idle = False
        for b in data:
            if b >= 0xC0:
                busy = bool(b & 0x04)
                if self._busy and not busy:
                    went_idle = True
                self._busy = busy
        return "".join(chr(b) for b in data if 0x20 <= b < 0x80), went_idle
