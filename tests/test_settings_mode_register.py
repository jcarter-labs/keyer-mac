"""Logic-only tests for the mode-register bit packing in keyer_mac.settings.

No serial/XMLRPC involved — Settings has zero file or hardware I/O, it
only packs/unpacks an in-memory dict. Runs headless (QT_QPA_PLATFORM=
offscreen, set in conftest.py) since Settings is still a real QDialog
loaded from settings.ui.
"""

from pathlib import Path

from keyer_mac.settings import Settings

SETTINGS_UI = Path(__file__).resolve().parent.parent / "keyer_mac" / "settings.ui"


def test_mode_register_round_trip_default():
    # Source's own fallback default (WinKeyer.setmode / Settings.setup).
    register = "11001110"
    pref = {"mode_register": register}
    dlg = Settings(SETTINGS_UI, pref)

    assert dlg.disable_paddle_watchdog.isChecked() is True   # bit 0 = '1'
    assert dlg.paddle_echo_back.isChecked() is True           # bit 1 = '1'
    assert dlg.key_mode.currentText() == "Iambic B"           # bits 2-3 = '00'
    assert dlg.paddle_swap.isChecked() is True                 # bit 4 = '1'
    assert dlg.serial_echo_back.isChecked() is True            # bit 5 = '1'
    assert dlg.auto_space.isChecked() is True                  # bit 6 = '1'
    assert dlg.ct_spacing.isChecked() is False                 # bit 7 = '0'

    # Round trip: no UI changes, save_changes() must reproduce the input exactly.
    dlg.save_changes()
    assert pref["mode_register"] == register


def test_mode_register_round_trip_all_flags_flipped():
    register = "00110001"
    pref = {"mode_register": register}
    dlg = Settings(SETTINGS_UI, pref)

    assert dlg.disable_paddle_watchdog.isChecked() is False
    assert dlg.paddle_echo_back.isChecked() is False
    assert dlg.key_mode.currentText() == "Bug Mode"            # bits 2-3 = '11'
    assert dlg.paddle_swap.isChecked() is False
    assert dlg.serial_echo_back.isChecked() is False
    assert dlg.auto_space.isChecked() is False
    assert dlg.ct_spacing.isChecked() is True

    dlg.save_changes()
    assert pref["mode_register"] == register


def test_mode_register_key_mode_maps_to_correct_bits():
    expected = {
        "Iambic B": "00",
        "Iambic A": "01",
        "Ultimatic": "10",
        "Bug Mode": "11",
    }
    for mode_name, bits in expected.items():
        pref = {"mode_register": "00000000"}
        dlg = Settings(SETTINGS_UI, pref)
        index = dlg.key_mode.findText(mode_name)
        assert index >= 0, f"{mode_name!r} not found in key_mode combo box"
        dlg.key_mode.setCurrentIndex(index)
        dlg.save_changes()
        assert pref["mode_register"][2:4] == bits
