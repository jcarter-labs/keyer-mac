"""Masterplan 4.3 (unit part): the speed dropdown."""

import json

import pytest

from keyer_mac import config
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
    return w


def test_dropdown_has_every_even_value_6_to_34_and_defaults_to_20(qtbot, cfg_path):
    w = make(qtbot)
    values = [w.speed_box.itemData(i) for i in range(w.speed_box.count())]
    assert values == list(range(6, 35, 2)) and len(values) == 15
    assert w.speed_box.currentData() == 20


def test_choosing_a_value_sends_it_once_and_saves_it(qtbot, cfg_path):
    w = make(qtbot)
    sent = []
    w.sig_set_speed.connect(sent.append)
    w.speed_box.setCurrentIndex(w.speed_box.findData(6))
    w.speed_box.setCurrentIndex(w.speed_box.findData(34))
    assert sent == [6, 34]
    assert json.loads(cfg_path.read_text())["speed"] == 34
    assert make(qtbot).speed_box.currentData() == 34          # relaunch


def test_speed_shown_from_elsewhere_is_not_sent_again_but_is_saved(qtbot, cfg_path):
    w = make(qtbot)
    sent = []
    w.sig_set_speed.connect(sent.append)
    w.show_speed(24)
    assert sent == [] and w.speed_box.currentData() == 24
    assert json.loads(cfg_path.read_text())["speed"] == 24
    w.show_speed(25)                                          # not in the list: ignored
    assert w.speed_box.currentData() == 24


def test_invalid_saved_speed_falls_back_to_20(qtbot, cfg_path):
    cfg_path.write_text(json.dumps({"speed": 35}))
    assert make(qtbot).speed_box.currentData() == 20
