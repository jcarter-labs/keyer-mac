"""Masterplan 3.2: port selection on fake port lists."""

from collections import namedtuple

from keyer_mac import ports

P = namedtuple("P", "device vid pid")

DEBUG = P("/dev/cu.debug-console", None, None)
BT = P("/dev/cu.Bluetooth-Incoming-Port", None, None)
SPEAKER = P("/dev/cu.OontZAngle3DSF35", None, None)
WK = P("/dev/cu.usbserial-8330", 0x1A86, 0x7523)
WK_MOVED = P("/dev/cu.usbserial-8340", 0x1A86, 0x7523)
FTDI = P("/dev/cu.usbserial-A1", 0x0403, 0x6001)


def test_virtual_only_yields_nothing_to_probe():
    assert ports.probe_order([DEBUG, BT, SPEAKER]) == []


def test_real_only():
    assert ports.probe_order([WK]) == [WK.device]


def test_mixed_picks_the_winkeyer_regardless_of_order():
    assert ports.probe_order([WK, DEBUG, BT]) == [WK.device]
    assert ports.probe_order([DEBUG, BT, WK]) == [WK.device]


def test_suffix_changed_saved_name_is_stale():
    # saved -8340, but the keyer now enumerates as -8330
    assert ports.probe_order([DEBUG, WK], saved="/dev/cu.usbserial-8340") == [WK.device]


def test_none_present():
    assert ports.probe_order([]) == []


def test_other_usb_serial_is_never_auto_probed():
    assert ports.probe_order([FTDI, WK]) == [WK.device]
    assert ports.probe_order([FTDI]) == []


def test_saved_virtual_port_is_ignored_but_manual_is_honored():
    assert ports.probe_order([DEBUG, WK], saved=DEBUG.device) == [WK.device]
    assert ports.probe_order([DEBUG, WK], manual=DEBUG.device) == [DEBUG.device, WK.device]


def test_saved_present_real_port_goes_first_without_duplicates():
    assert ports.probe_order([WK, WK_MOVED], saved=WK_MOVED.device) == [WK_MOVED.device, WK.device]


def test_a_virtual_port_is_never_saved():
    assert not ports.should_save(DEBUG.device, [DEBUG, WK])
    assert not ports.should_save("/dev/cu.gone", [WK])
    assert ports.should_save(WK.device, [DEBUG, WK])
