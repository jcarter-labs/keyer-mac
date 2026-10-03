"""'... ' after each sent message, Enter in free text never reaches the keyer,
and control bytes are never sent as text (they are keyer commands)."""

import pytest

from keyer_mac import config
from keyer_mac.ui import END_OF_MESSAGE, MainWindow
from keyer_mac.winkeyer import WinKeyer
from keyer_mac.worker import Worker

from test_winkeyer import make  # fake serial + deterministic clock


# ---- protocol layer --------------------------------------------------------------

def test_send_text_drops_control_bytes_that_are_keyer_commands():
    wk, port, _ = make()
    wk.send_text("A\nB\rC\x1bD\x00E")
    assert port.written == [b"ABCDE"]
    wk.send_text("\n\r")                       # nothing sendable: nothing written
    assert port.written == [b"ABCDE"]


def test_poll_with_status_reports_busy_to_idle_once():
    wk, port, _ = make()
    port._inbox = b"\xc4E\xc0"
    assert wk.poll_with_status() == ("E", True)
    port._inbox = b"\xc0"                       # idle again, no transition
    assert wk.poll_with_status() == ("", False)
    port._inbox = b"\xc4"
    assert wk.poll_with_status() == ("", False)  # idle -> busy is not "went idle"


# ---- window layer ------------------------------------------------------------------

@pytest.fixture
def win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "cfg.json"))
    w = MainWindow(Worker(list_ports=lambda: [], auto_poll=False), cfg=config.load(), list_ports=lambda: [])
    qtbot.addWidget(w)
    w.sent, w.back = [], []
    w.sig_send_text.connect(w.sent.append)
    w.sig_backspace.connect(lambda: w.back.append(1))
    return w


def echo_line(w):
    return "".join(e[2] for e in w.message.entries if e[0] == "echo")


def test_marker_follows_the_last_echoed_character_of_a_message(win):
    win.msg_fields[0].setText("CQ")
    win.msg_buttons[0].click()
    win._on_echo("C")
    assert echo_line(win) == "C"
    win._on_echo("Q")
    assert echo_line(win) == "CQ" + END_OF_MESSAGE == "CQ... "


def test_queued_messages_each_get_a_marker(win):
    win.msg_fields[0].setText("A"); win.msg_fields[1].setText("B")
    win.msg_buttons[0].click(); win.msg_buttons[1].click()
    win._on_echo("AB")
    assert echo_line(win) == "A... B... "


def test_free_text_gets_no_marker_and_enter_does_nothing(win):
    for chunk in ("E", "\n", "T", " ", "A"):
        win.free_text.insertPlainText(chunk)
    assert win.sent == ["E", "T", " ", "A"]       # Enter never reaches the keyer
    assert win._marks == []                       # and creates no marker
    win._on_echo("ET A")
    assert echo_line(win) == "ET A"


def test_free_text_never_produces_an_ellipsis_whatever_the_echo_and_idle_timing(win):
    """Typing, echoes and idle events interleaved every way: no '...' ever."""
    for ch in "CQ DE N6YU":
        win.free_text.insertPlainText(ch)
        win._on_echo(ch)
        win._on_idle()
    win.free_text.insertPlainText("\n")
    win._on_idle()
    assert "..." not in echo_line(win)
    assert echo_line(win) == "CQ DE N6YU"


def test_pasted_multiline_text_is_sent_without_markers(win):
    win.free_text.insertPlainText("AB\nCD")
    assert win.sent == ["ABCD"]
    win._on_echo("ABCD")
    assert echo_line(win) == "ABCD"


def test_deleting_a_newline_sends_no_backspace_but_deleting_a_letter_does(win):
    win.free_text.insertPlainText("E\n")
    win.free_text.textCursor().deletePreviousChar()      # removes the newline
    assert win.back == []
    win.free_text.textCursor().deletePreviousChar()      # removes the E
    assert len(win.back) == 1


def test_erasing_unsent_characters_pulls_the_counts_back(win):
    win.free_text.insertPlainText("AB")
    win.free_text.textCursor().deletePreviousChar()      # B not yet echoed: unsent
    assert win._sent_chars == 1


def test_idle_closes_a_message_whose_marker_never_came_and_resyncs(win):
    win.msg_fields[0].setText("AB"); win.msg_buttons[0].click()
    win._on_echo("A")                                     # B was never echoed
    assert echo_line(win) == "A"
    win._on_idle()
    assert echo_line(win) == "A... "
    assert win._marks == [] and win._echo_chars == win._sent_chars == 2


def test_idle_with_nothing_pending_adds_nothing(win):
    win._on_echo("E")
    win._on_idle()
    assert echo_line(win) == "E"


def test_xmlrpc_strings_get_a_marker_and_control_bytes_are_dropped(win):
    win._bridge_send_string("CQ\n")
    assert win.sent == ["CQ"]
    win._on_echo("CQ")
    assert echo_line(win).endswith("CQ... ")


def test_counts_reset_on_a_new_connection(win):
    win.msg_fields[0].setText("A"); win.msg_buttons[0].click()
    win._on_found("/dev/cu.usbserial-X", 0x1F, 20)
    assert win._marks == [] and win._sent_chars == win._echo_chars == 0
