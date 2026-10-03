"""Port dropdown (Spec feature 1): lists every port, a pick or typed port is
tried at once, found selects the port, and a newly enumerated WK-mini is tried
without waiting for the retry backoff."""

from collections import namedtuple

import pytest

from keyer_mac import config
from keyer_mac.ui import MainWindow
from keyer_mac.worker import Worker

P = namedtuple("P", "device vid pid description")
DEBUG = P("/dev/cu.debug-console", None, None, "n/a")
WK = P("/dev/cu.usbserial-8330", 0x1A86, 0x7523, "USB Serial")


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(p))
    return p


class Rig:
    def __init__(self, qtbot, ports):
        self.ports = list(ports)
        self.win = MainWindow(Worker(list_ports=lambda: self.ports, auto_poll=False),
                              cfg=config.load(), list_ports=lambda: self.ports)
        qtbot.addWidget(self.win)
        self.scans = []
        self.win.worker.scan_requested.disconnect()        # keep the worker idle
        self.win.worker.scan_requested.connect(lambda *a: self.scans.append(a))


def test_dropdown_lists_every_port_virtual_ones_included_with_tooltips(qtbot, cfg_path):
    r = Rig(qtbot, [DEBUG, WK])
    box = r.win.port_box
    # shown without the "/dev/cu." prefix; the full path is the item data and in the tooltip
    assert [box.itemText(i) for i in range(box.count())] == ["debug-console", "usbserial-8330"]
    assert [box.itemData(i) for i in range(box.count())] == [DEBUG.device, WK.device]
    assert box.itemData(1, 3) == "/dev/cu.usbserial-8330  (USB Serial)"   # Qt.ToolTipRole == 3
    assert box.isEditable()


def test_dropdown_is_190_wide(qtbot, cfg_path):
    r = Rig(qtbot, [WK])
    assert r.win.port_box.maximumWidth() == r.win.port_box.minimumWidth() == 190


def test_picking_a_port_starts_a_scan_with_it_as_manual(qtbot, cfg_path):
    r = Rig(qtbot, [DEBUG, WK])
    r.win.port_box.setCurrentIndex(1)
    r.win.port_box.activated.emit(1)
    saved, manual, mode, speed = r.scans[-1]
    assert manual == WK.device and speed == 20


def test_typing_a_port_and_pressing_enter_starts_a_scan(qtbot, cfg_path):
    r = Rig(qtbot, [WK])
    r.win.port_box.lineEdit().setText("/dev/cu.typed")
    r.win.port_box.lineEdit().editingFinished.emit()
    assert r.scans[-1][1] == "/dev/cu.typed"


def test_found_selects_the_port_without_starting_another_scan(qtbot, cfg_path):
    r = Rig(qtbot, [WK])
    r.win._on_found(WK.device, 0x1F, 20)
    assert r.win.port_box.currentText() == "usbserial-8330"
    assert r.win.port_box.toolTip() == WK.device                 # full path on hover
    assert r.scans == []


def test_a_newly_enumerated_keyer_is_tried_at_once(qtbot, cfg_path):
    r = Rig(qtbot, [DEBUG])
    r.win.start_scan()
    n = len(r.scans)
    r.win._watch_ports()                       # nothing new: no extra scan
    assert len(r.scans) == n
    r.ports.append(WK)                         # plug in
    r.win._watch_ports()
    assert len(r.scans) == n + 1
    r.win._watch_ports()                       # same list again: no repeat
    assert len(r.scans) == n + 1


def test_the_watch_is_idle_while_a_keyer_is_connected(qtbot, cfg_path):
    r = Rig(qtbot, [DEBUG])
    r.win.start_scan()
    r.win._on_found(WK.device, 0x1F, 20)
    n = len(r.scans)
    r.ports.append(WK)
    r.win._watch_ports()
    assert len(r.scans) == n


def test_a_typed_short_name_or_full_path_resolves_to_the_full_device(qtbot, cfg_path):
    r = Rig(qtbot, [WK])
    r.win.port_box.lineEdit().setText("usbserial-1")
    r.win.port_box.lineEdit().editingFinished.emit()
    assert r.scans[-1][1] == "/dev/cu.usbserial-1"
    r.win.port_box.lineEdit().setText("/dev/tty.usbserial-2")
    r.win.port_box.lineEdit().editingFinished.emit()
    assert r.scans[-1][1] == "/dev/tty.usbserial-2"


def test_port_name_helpers():
    from keyer_mac.ui import full_port_name, short_port_name
    assert short_port_name("/dev/cu.usbserial-8330") == "usbserial-8330"
    assert short_port_name("/dev/tty.x") == "/dev/tty.x"
    assert full_port_name("usbserial-8330") == "/dev/cu.usbserial-8330"
    assert full_port_name("/dev/cu.a") == "/dev/cu.a" and full_port_name("  ") == ""


def test_header_controls_are_grouped_on_the_right_ten_apart(qtbot, cfg_path):
    r = Rig(qtbot, [WK])
    w = r.win
    w.show()
    gap_info_gear = w.gear.x() - (w.info_button.x() + w.info_button.width())
    gap_gear_port = w.port_box.x() - (w.gear.x() + w.gear.width())
    assert gap_info_gear == gap_gear_port == 10
    assert w.header_label.x() < w.info_button.x() - 100          # label stays far left
    assert w.info_button.height() == w.gear.height() == w.port_box.height() == 26


def test_speed_box_is_wide_enough_for_its_popup_and_the_gear_glyph_is_big(qtbot, cfg_path):
    r = Rig(qtbot, [WK])
    assert r.win.speed_box.width() >= 60
    assert r.win.gear.font().pointSize() == 20
    assert r.win.port_box.font().pointSize() == 14
