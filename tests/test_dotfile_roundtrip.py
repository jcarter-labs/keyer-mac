"""Logic-only test for ~/.keyer-mac.json persistence in keyer_mac.__main__.

Uses KEYER_MAC_CONFIG_PATH to redirect the dotfile into pytest's tmp_path
(Constitution rule 10) — never touches the operator's real $HOME. Runs
headless (QT_QPA_PLATFORM=offscreen, set in conftest.py).

Serial/XMLRPC behavior is intentionally out of scope here — that's
covered only by the live diagnostics in tools/winkeyer_*_diagnostic.py,
per the masterplan's Verification Standard. Instantiating WinKeyer
directly (not importing __main__'s module-level singleton) never calls
host_init(), so no hardware is touched by these tests either way.
"""

import json


def test_dotfile_round_trip(monkeypatch, tmp_path):
    config_file = tmp_path / "keyer-mac-test.json"
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(config_file))

    from keyer_mac.__main__ import WinKeyer

    win = WinKeyer()  # loadsaved() runs here; no config_file yet -> writes defaults
    assert config_file.exists()

    # setText() fires textChanged -> savestuff(), matching real UI behavior.
    win.msg1.setText("CQ FD K6GTE K")
    win.msg2.setText("TU 1B ORG")
    win.msg6.setText("73")

    saved = json.loads(config_file.read_text())
    assert saved["1"] == "CQ FD K6GTE K"
    assert saved["2"] == "TU 1B ORG"
    assert saved["6"] == "73"

    # Round trip: a fresh instance pointed at the same file loads it back.
    win2 = WinKeyer()
    assert win2.msg1.text() == "CQ FD K6GTE K"
    assert win2.msg2.text() == "TU 1B ORG"
    assert win2.msg6.text() == "73"


def test_dotfile_defaults_written_when_missing(monkeypatch, tmp_path):
    config_file = tmp_path / "does-not-exist-yet.json"
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(config_file))
    assert not config_file.exists()

    from keyer_mac.__main__ import WinKeyer

    WinKeyer()

    assert config_file.exists()
    saved = json.loads(config_file.read_text())
    assert saved.get("1") == ""
    assert "device" in saved
