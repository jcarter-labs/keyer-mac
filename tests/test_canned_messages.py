"""Masterplan 4.2 (unit part): five fields, "msg N" buttons, save on every edit."""

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


def make(qtbot, cfg=None):
    w = MainWindow(Worker(list_ports=lambda: []), cfg=cfg if cfg is not None else config.load())
    qtbot.addWidget(w)
    return w


def test_five_rows_with_msg_n_buttons(qtbot, cfg_path):
    w = make(qtbot)
    assert [b.text() for b in w.msg_buttons] == [f"msg {n}" for n in range(1, 6)]
    assert len(w.msg_fields) == 5
    assert all(b.width() <= 65 for b in w.msg_buttons)


def test_every_edit_is_saved_at_once_and_restored_on_relaunch(qtbot, cfg_path):
    w = make(qtbot)
    w.msg_fields[0].setText("CQ TEST")
    assert json.loads(cfg_path.read_text())["1"] == "CQ TEST"
    w.msg_fields[4].setText("73")
    saved = json.loads(cfg_path.read_text())
    assert saved["5"] == "73" and saved["1"] == "CQ TEST"
    w2 = make(qtbot)                                   # relaunch: loads the file
    assert w2.msg_fields[0].text() == "CQ TEST" and w2.msg_fields[4].text() == "73"


def test_button_n_sends_its_own_text_and_empty_sends_nothing(qtbot, cfg_path):
    w = make(qtbot)
    sent = []
    w.sig_send_text.connect(sent.append)
    w.msg_fields[1].setText("tu 73")
    w.msg_fields[2].setText("599")
    w.msg_buttons[1].click()
    w.msg_buttons[2].click()
    w.msg_buttons[3].click()                           # empty field
    assert sent == ["tu 73", "599"]


def test_leftover_key_6_is_ignored_and_dropped(qtbot, cfg_path):
    cfg_path.write_text(json.dumps({"1": "A", "6": "OLD"}))
    w = make(qtbot)
    assert w.msg_fields[0].text() == "A"
    w.msg_fields[1].setText("B")
    assert "6" not in json.loads(cfg_path.read_text())
