"""Masterplan 4.5 (unit part): the six XMLRPC methods reach the worker /
window through the real MainWindow, on a real worker thread."""

import xmlrpc.client

import pytest
from PyQt6.QtCore import pyqtSlot

from keyer_mac import config
from keyer_mac.ui import MainWindow
from keyer_mac.worker import Worker


class RecordingWorker(Worker):
    def __init__(self):
        super().__init__(list_ports=lambda: [], auto_poll=False)
        self.calls = []

    @pyqtSlot(str)
    def send_text(self, text): self.calls.append(("send_text", text))

    @pyqtSlot(str)
    def send_blended(self, text): self.calls.append(("send_blended", text))

    @pyqtSlot()
    def tune_on(self): self.calls.append(("tune_on",))

    @pyqtSlot()
    def tune_off(self): self.calls.append(("tune_off",))

    @pyqtSlot()
    def clear_buffer(self): self.calls.append(("clear_buffer",))

    @pyqtSlot(int)
    def set_speed(self, wpm): self.calls.append(("set_speed", wpm))


@pytest.fixture
def rig(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("KEYER_MAC_CONFIG_PATH", str(tmp_path / "cfg.json"))
    worker = RecordingWorker()
    win = MainWindow(worker, cfg=config.load(), list_ports=lambda: [],
                     start_bridge=True, bridge_host="127.0.0.1", bridge_port=0)
    qtbot.addWidget(win)
    win._thread.start()
    win._connected = True
    proxy = xmlrpc.client.ServerProxy(f"http://127.0.0.1:{win.bridge.port}")
    yield win, worker, proxy
    win.shutdown()


def test_all_six_methods_reach_the_worker_and_setspeed_moves_the_dropdown(rig, qtbot):
    win, worker, p = rig
    p.k1elsendstring("CQ"); p.sendblended("AR"); p.tuneon(); p.tuneoff(); p.clearbuffer(); p.setspeed(24)
    qtbot.waitUntil(lambda: len(worker.calls) == 6, timeout=3000)
    assert sorted(worker.calls) == sorted([
        ("send_text", "CQ"), ("send_blended", "AR"), ("tune_on",), ("tune_off",),
        ("clear_buffer",), ("set_speed", 24)])
    assert win.speed_box.currentData() == 24          # dropdown follows XMLRPC


def test_disconnected_call_is_dropped_and_noted_in_the_message_box(rig, qtbot):
    win, worker, p = rig
    win._connected = False
    p.k1elsendstring("X")
    qtbot.waitUntil(lambda: any("dropped" in l for l in win.message.lines), timeout=3000)
    assert worker.calls == []


def test_bad_speed_is_a_fault_and_changes_nothing(rig):
    win, worker, p = rig
    with pytest.raises(xmlrpc.client.Fault):
        p.setspeed(25)
    assert win.speed_box.currentData() == 20
