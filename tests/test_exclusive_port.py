"""A second program is refused at once (kernel behaviour, tested on a pseudo-terminal
so no hardware is touched), and the refusal is explained."""

import errno
import os
import pty

import pytest
import serial

from keyer_mac import winkeyer


@pytest.fixture
def pty_path():
    master, slave = pty.openpty()
    try:
        yield os.ttyname(slave)
    finally:
        os.close(master)
        os.close(slave)


def test_second_exclusive_open_is_refused_and_first_still_works(pty_path):
    try:
        first = winkeyer.open_port(pty_path)
    except serial.SerialException as exc:        # pty without modem-control support
        pytest.skip(f"cannot open a pseudo-terminal the WinKeyer way here: {exc}")
    try:
        with pytest.raises(serial.SerialException) as err:
            winkeyer.open_port(pty_path)
        assert winkeyer.port_in_use(err.value)
        assert "in use by another program" in winkeyer.describe_open_error(pty_path, err.value)
        assert first.is_open
    finally:
        first.close()
    winkeyer.open_port(pty_path).close()           # free again after the first closes


@pytest.mark.parametrize("exc,busy", [
    (serial.SerialException("Could not exclusively lock port /dev/x: [Errno 35] Resource temporarily unavailable"), True),
    (serial.SerialException("could not open port /dev/x: [Errno 16] Resource busy"), True),
    (OSError(errno.EBUSY, "Resource busy"), True),
    (serial.SerialException("device reports readiness to read but returned no data (device disconnected or multiple access on port?)"), True),
    (serial.SerialException("could not open port /dev/x: [Errno 2] No such file or directory"), False),
    (serial.SerialException("permission denied"), False),
])
def test_port_in_use_classification(exc, busy):
    assert winkeyer.port_in_use(exc) is busy


def test_describe_other_errors_keeps_the_system_text():
    exc = serial.SerialException("permission denied")
    assert winkeyer.describe_open_error("/dev/x", exc) == "/dev/x could not be used: permission denied"
