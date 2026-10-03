"""Masterplan 4.6: the Info dialog opens with the summary line, lists every
required item, and closing changes nothing."""

import json

import pytest

import keyer_mac
from keyer_mac import config
from keyer_mac.ui import INFO_SUMMARY, InfoDialog, MainWindow, info_text
from keyer_mac.worker import Worker


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "cfg.json"))
    w = MainWindow(Worker(list_ports=lambda: [], auto_poll=False), cfg=config.load(),
                   list_ports=lambda: [], start_bridge=True, bridge_host="127.0.0.1", bridge_port=0)
    qtbot.addWidget(w)
    yield w
    w.shutdown()


def test_summary_line_comes_first_and_says_what_the_app_is():
    text = info_text("/dev/cu.usbserial-1", 0x1F, "/x/cfg.json", "0.0.0.0:8000")
    assert text.splitlines()[0] == INFO_SUMMARY
    assert INFO_SUMMARY == "Keyer-mac is an auto keyer written for the Mac to interface with a WinKeyer Mini via USB."


def test_every_required_item_is_listed():
    text = info_text("/dev/cu.usbserial-1", 0x1F, "/x/cfg.json", "0.0.0.0:8000")
    for needle in (f"Version: {keyer_mac.__version__}", "/dev/cu.usbserial-1", "WinKeyer firmware: v3.1",
                   "/x/cfg.json", "0.0.0.0:8000", "k1elsendstring", "setspeed", "sendblended", "tuneon",
                   "tuneoff", "clearbuffer", "Michael Bridak", "GPL-3.0-or-later",
                   "Designed to work with the K1EL WinKeyer Mini", "jcarter-labs/keyer-mac",
                   "https://github.com/jcarter-labs/keyer-mac"):
        assert needle in text, needle


def test_not_connected_shows_none_and_no_firmware():
    text = info_text(None, None, "/x", "off")
    assert "Connected port: none" in text and "not connected" in text


def test_window_body_reflects_the_connection_and_the_bridge(win):
    assert "Connected port: none" in win.info_body()
    assert f"127.0.0.1:{win.bridge.port}" in win.info_body()
    win._on_found("/dev/cu.usbserial-8330", 0x1F, 20)
    win.worker.device = "/dev/cu.usbserial-8330"
    body = win.info_body()
    assert "/dev/cu.usbserial-8330" in body and "v3.1" in body


def test_dialog_shows_the_text_and_closing_changes_nothing(win, qtbot):
    before = dict(win.cfg)
    d = InfoDialog(win.info_body(), win)
    qtbot.addWidget(d)
    assert d.body.toPlainText().splitlines()[0] == INFO_SUMMARY
    d.reject()
    assert win.cfg == before


def test_info_button_sits_left_of_the_gear_in_row_0(win):
    win.show()
    assert win.info_button.y() == win.gear.y() < win.message.y()
    assert win.header_label.x() < win.info_button.x() < win.gear.x() < win.port_box.x()


def test_version_constants():
    assert keyer_mac.__version__ == "1.1"
    assert len(keyer_mac.__build_date__) == 10
