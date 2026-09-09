"""Tests for the real-vs-virtual serial device auto-selection heuristic.

Covers the incident in deviation-log.md #7: `~/.keyer-mac.json` ended up
with a macOS virtual/compatibility port
(`/dev/cu.Bluetooth-Incoming-Port`) saved as the WinKeyer device, which
opens fine at the OS level but never responds, because nothing real is
behind it.

Monkeypatches `serial.tools.list_ports.comports` (imported into
keyer_mac.__main__ as `comports`) so no real hardware or OS port
enumeration is touched. Uses KEYER_MAC_CONFIG_PATH to redirect the
dotfile into pytest's tmp_path (Constitution rule 10), same pattern as
tests/test_dotfile_roundtrip.py. Runs headless (QT_QPA_PLATFORM=offscreen,
set in conftest.py).
"""

import json


class FakePort:
    """Minimal stand-in for pyserial's ListPortInfo — only the attributes
    keyer_mac.__main__ actually reads (device, description, vid)."""

    def __init__(self, device, description="n/a", vid=None):
        self.device = device
        self.description = description
        self.vid = vid


# The four real ports seen on the operator's machine the night of the
# incident (see the task's `comports()` transcript): three virtual/
# compatibility entries (vid None, description "n/a") enumerated before
# the one real USB serial adapter (vid set, meaningful description).
DEBUG_CONSOLE = FakePort("/dev/cu.debug-console", description="n/a", vid=None)
BLUETOOTH_INCOMING = FakePort("/dev/cu.Bluetooth-Incoming-Port", description="n/a", vid=None)
BLUETOOTH_ACCESSORY = FakePort("/dev/cu.OontZAngle3DSF35", description="n/a", vid=None)
REAL_USBSERIAL = FakePort("/dev/cu.usbserial-8340", description="USB Serial", vid=0x0403)


def test_auto_select_prefers_real_device_over_virtual_enumerated_last(monkeypatch, tmp_path):
    """
    Reproduces the exact incident ordering: the real USB device is
    enumerated *before* virtual ports, so the old "last one wins" logic
    would default to a virtual port. The hardened heuristic must still
    pick the real device.
    """
    config_file = tmp_path / "keyer-mac-test.json"
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(config_file))
    assert not config_file.exists()

    import keyer_mac.__main__ as km

    monkeypatch.setattr(
        km,
        "comports",
        lambda include_links=True: [
            REAL_USBSERIAL,
            DEBUG_CONSOLE,
            BLUETOOTH_INCOMING,
            BLUETOOTH_ACCESSORY,
        ],
    )

    win = km.WinKeyer()

    assert win.device == "/dev/cu.usbserial-8340"
    saved = json.loads(config_file.read_text())
    assert saved["device"] == "/dev/cu.usbserial-8340"


def test_auto_select_prefers_real_device_regardless_of_enumeration_order(monkeypatch, tmp_path):
    """Same as above but with the real device enumerated last — the
    heuristic must not depend on where in the list it falls."""
    config_file = tmp_path / "keyer-mac-test.json"
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(config_file))

    import keyer_mac.__main__ as km

    monkeypatch.setattr(
        km,
        "comports",
        lambda include_links=True: [
            DEBUG_CONSOLE,
            BLUETOOTH_INCOMING,
            BLUETOOTH_ACCESSORY,
            REAL_USBSERIAL,
        ],
    )

    win = km.WinKeyer()

    assert win.device == "/dev/cu.usbserial-8340"


def test_auto_select_falls_back_to_last_enumerated_when_nothing_real(monkeypatch, tmp_path):
    """
    No real device present at all: falls back to source's original
    "last enumerated" behavior rather than an empty string, since some
    default is still better than none and there is nothing to
    distinguish among purely virtual entries.
    """
    config_file = tmp_path / "keyer-mac-test.json"
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(config_file))

    import keyer_mac.__main__ as km

    monkeypatch.setattr(
        km,
        "comports",
        lambda include_links=True: [DEBUG_CONSOLE, BLUETOOTH_INCOMING, BLUETOOTH_ACCESSORY],
    )

    win = km.WinKeyer()

    assert win.device == "/dev/cu.OontZAngle3DSF35"  # last of the (all-virtual) list


def test_auto_select_handles_empty_port_list(monkeypatch, tmp_path):
    """No ports enumerated at all (e.g. nothing plugged in) — must not
    crash, and should end up with an empty device rather than raising."""
    config_file = tmp_path / "keyer-mac-test.json"
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(config_file))

    import keyer_mac.__main__ as km

    monkeypatch.setattr(km, "comports", lambda include_links=True: [])

    win = km.WinKeyer()

    assert win.device == ""


def test_explicit_saved_device_is_still_respected_even_if_virtual(monkeypatch, tmp_path):
    """
    Manual/previously-saved selection must still win over the
    auto-selection heuristic — including a virtual device — so a user
    who deliberately picked one (or an old bad save from before this
    fix) isn't silently overridden on the next launch. Only the
    *initial* auto-pick is hardened; a real saved value is always
    honored verbatim, per the deviation-log.md #7 design decision.
    """
    config_file = tmp_path / "keyer-mac-test.json"
    config_file.write_text(
        json.dumps(
            {
                "device": "/dev/cu.Bluetooth-Incoming-Port",
                "1": "",
                "2": "",
                "3": "",
                "4": "",
                "5": "",
                "6": "",
            }
        )
    )
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(config_file))

    import keyer_mac.__main__ as km

    monkeypatch.setattr(
        km,
        "comports",
        lambda include_links=True: [REAL_USBSERIAL, BLUETOOTH_INCOMING],
    )

    win = km.WinKeyer()

    assert win.device == "/dev/cu.Bluetooth-Incoming-Port"


def test_missing_saved_device_key_falls_back_to_auto_selected_real_device(monkeypatch, tmp_path):
    """
    A saved config with no usable "device" value at all (missing key)
    is the "no valid saved device to fall back to" case the task calls
    out — this should get the real-hardware-preferring auto pick, not
    an empty string or a crash.
    """
    config_file = tmp_path / "keyer-mac-test.json"
    config_file.write_text(json.dumps({"1": "", "2": "", "3": "", "4": "", "5": "", "6": ""}))
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(config_file))

    import keyer_mac.__main__ as km

    monkeypatch.setattr(
        km,
        "comports",
        lambda include_links=True: [BLUETOOTH_INCOMING, REAL_USBSERIAL],
    )

    win = km.WinKeyer()

    assert win.device == "/dev/cu.usbserial-8340"


def test_empty_saved_device_falls_back_to_auto_selected_real_device(monkeypatch, tmp_path):
    """Same as above but with "device": "" explicitly present rather than
    the key being absent."""
    config_file = tmp_path / "keyer-mac-test.json"
    config_file.write_text(
        json.dumps({"device": "", "1": "", "2": "", "3": "", "4": "", "5": "", "6": ""})
    )
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(config_file))

    import keyer_mac.__main__ as km

    monkeypatch.setattr(
        km,
        "comports",
        lambda include_links=True: [BLUETOOTH_INCOMING, REAL_USBSERIAL],
    )

    win = km.WinKeyer()

    assert win.device == "/dev/cu.usbserial-8340"


def test_is_real_serial_port_heuristic_directly():
    """Unit-level check of the heuristic itself against the four
    real-world entries seen on the operator's machine."""
    from keyer_mac.__main__ import _is_real_serial_port

    assert _is_real_serial_port(REAL_USBSERIAL) is True
    assert _is_real_serial_port(DEBUG_CONSOLE) is False
    assert _is_real_serial_port(BLUETOOTH_INCOMING) is False
    assert _is_real_serial_port(BLUETOOTH_ACCESSORY) is False

    # vid set but description also "n/a" — vid alone is sufficient.
    assert _is_real_serial_port(FakePort("/dev/cu.usbmodemXYZ", description="n/a", vid=0x2341)) is True

    # No vid, but a real-looking, non-"n/a" description — still counted
    # as real (secondary signal fallback for backends that don't
    # populate vid).
    assert (
        _is_real_serial_port(FakePort("/dev/ttyUSB0", description="FTDI USB Serial", vid=None))
        is True
    )
