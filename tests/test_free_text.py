"""Masterplan 4.1 (unit part): free-text edits become keyer bytes."""

import pytest

from keyer_mac import config
from keyer_mac.ui import MainWindow, MessageBox, diff_edit
from keyer_mac.worker import Worker


@pytest.mark.parametrize("old,new,expected", [
    ("", "T", (0, "T")),
    ("TES", "TEST", (0, "T")),
    ("TEST", "TES", (1, "")),
    ("TEST", "", (4, "")),
    ("TEST", "TEXT", (2, "XT")),       # replace in the middle: erase back, resend
    ("AB", "AB", (0, "")),
    ("cq", "cq de", (0, " de")),
])
def test_diff_edit(old, new, expected):
    assert diff_edit(old, new) == expected


@pytest.fixture
def win(qtbot):
    w = MainWindow(Worker(list_ports=lambda: []), cfg=config.defaults())
    qtbot.addWidget(w)
    sent, back = [], []
    w.sig_send_text.connect(sent.append)
    w.sig_backspace.connect(lambda: back.append(1))
    w.sent, w.back = sent, back
    return w


def test_typing_emits_each_character_and_deleting_emits_backspaces(win):
    for ch in "TEST":
        win.free_text.insertPlainText(ch)
    assert win.sent == ["T", "E", "S", "T"] and win.back == []
    win.free_text.textCursor().deletePreviousChar()
    win.free_text.textCursor().deletePreviousChar()
    assert len(win.back) == 2


def test_pasting_sends_the_whole_text_once(win):
    win.free_text.insertPlainText("cq cq")
    assert win.sent == ["cq cq"]


def test_message_box_free_text_is_three_lines_high_and_scrolls(win):
    fm = win.free_text.fontMetrics()
    assert win.free_text.height() < 5 * fm.lineSpacing()
    assert win.free_text.height() >= 3 * fm.lineSpacing()


def test_message_box_countdown_in_place_status_appends_echo_accumulates(qtbot):
    box = MessageBox()
    qtbot.addWidget(box)
    box.set_countdown("Scanning for keyer… 8")
    box.set_countdown("Scanning for keyer… 7")
    assert box.lines == ["Scanning for keyer… 7"]
    box.add_line("Keyer found")               # replaces the countdown line
    assert box.lines == ["Keyer found"]
    box.add_line("Keyer found")               # identical consecutive line: not repeated
    assert box.lines == ["Keyer found"]
    box.add_echo("TE")
    box.add_echo("ST")
    assert box.lines == ["Keyer found", "TEST"]
    box.add_line("Keyer disconnected.")
    assert box.lines[-1] == "Keyer disconnected."
    box.clear_all()
    assert box.lines == [] and box.toPlainText() == ""
