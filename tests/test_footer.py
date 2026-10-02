"""Masterplan 4.7: the footer shows the build date (bottom-left) and the
version (bottom-right), from the two constants, not from the clock."""

import datetime

import pytest

import keyer_mac
from keyer_mac import config
from keyer_mac.ui import MainWindow
from keyer_mac.worker import Worker


@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "cfg.json"))
    w = MainWindow(Worker(list_ports=lambda: [], auto_poll=False), cfg=config.load(), list_ports=lambda: [])
    qtbot.addWidget(w)
    return w


def test_footer_text_equals_the_constants(win):
    assert win.date_label.text() == keyer_mac.__build_date__
    assert win.version_label.text() == f"v{keyer_mac.__version__}" == "v1.1"


def test_footer_is_the_last_row_left_and_right(win):
    g = win.grid
    rd, cd, *_ = g.getItemPosition(g.indexOf(win.date_label))
    rv, cv, *_ = g.getItemPosition(g.indexOf(win.version_label))
    assert rd == rv == 9 and cd < cv
    assert win.date_label.font().pointSize() == win.version_label.font().pointSize() == 11


def test_date_is_a_valid_iso_date_and_not_read_from_the_clock(win, monkeypatch):
    datetime.date.fromisoformat(keyer_mac.__build_date__)
    class Boom(datetime.date):
        @classmethod
        def today(cls): raise AssertionError("footer must not read the clock")
    monkeypatch.setattr(datetime, "date", Boom)
    assert win.date_label.text() == keyer_mac.__build_date__
