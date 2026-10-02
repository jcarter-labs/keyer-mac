"""Masterplan 4.4 (unit part): the gear opens the dialog; Save packs the
mode register, writes it and saves it; Cancel changes nothing."""

import json

import pytest

from keyer_mac import config
from keyer_mac.settings import Settings
from keyer_mac.ui import MainWindow
from keyer_mac.worker import Worker


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(p))
    return p


def make(qtbot):
    w = MainWindow(Worker(list_ports=lambda: []), cfg=config.load())
    qtbot.addWidget(w)
    sent = []
    w.sig_set_mode.connect(sent.append)
    w.sent_modes = sent
    return w


def test_save_sends_and_stores_the_chosen_bits(qtbot, cfg_path, monkeypatch):
    w = make(qtbot)

    def fake_exec(self):
        self.key_mode.setCurrentText("Iambic A")       # bits 2-3 -> 01
        self.paddle_swap.setChecked(False)             # bit 4 -> 0
        self.save_changes()
        return 1

    monkeypatch.setattr(Settings, "exec", fake_exec)
    w.gear.click()
    # default 11001110 -> iambic A (01) at bits 2-3, paddle swap off
    assert w.cfg["mode_register"] == "11010110"
    assert w.sent_modes == [0b11010110]
    assert json.loads(cfg_path.read_text())["mode_register"] == "11010110"


def test_cancel_changes_nothing(qtbot, cfg_path, monkeypatch):
    w = make(qtbot)

    def fake_exec(self):
        self.key_mode.setCurrentText("Bug Mode")       # edited but not saved
        return 0

    monkeypatch.setattr(Settings, "exec", fake_exec)
    w.gear.click()
    assert w.cfg["mode_register"] == "11001110"
    assert w.sent_modes == []
    assert not cfg_path.exists()
