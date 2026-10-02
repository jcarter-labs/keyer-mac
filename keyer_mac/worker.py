"""Serial worker (masterplan Tech, module 4). Lives in its own QThread so the
UI thread never sleeps or waits on the keyer. Talks to the UI only through
signals. This is the Stage 2 slice: scan and connect. Reconnect, backoff and
the send queue arrive in Stage 3.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from keyer_mac import ports as ports_mod
from keyer_mac import winkeyer


class Worker(QObject):
    found = pyqtSignal(str, int, int)   # device, version byte, speed sent
    missing = pyqtSignal()
    scan_requested = pyqtSignal(object, object, int, int)  # saved, manual, mode, speed

    def __init__(self, open_port=winkeyer.open_port, list_ports=ports_mod.list_ports):
        super().__init__()
        self._open_port = open_port
        self._list_ports = list_ports
        self.port = None
        self.keyer: winkeyer.WinKeyer | None = None
        self.scan_requested.connect(self.scan)

    @pyqtSlot(object, object, int, int)
    def scan(self, saved, manual, mode_register, speed):
        """Try each candidate in order; on the first that answers and passes
        initialization, keep its port open and emit `found`. Otherwise `missing`."""
        for device in ports_mod.probe_order(self._list_ports(), saved, manual):
            port = None
            try:
                port = self._open_port(device)
                keyer = winkeyer.WinKeyer(port)
                version = keyer.host_open()
                if version is not None and keyer.initialize(mode_register, speed):
                    self.port, self.keyer = port, keyer
                    self.found.emit(device, version, speed)
                    return
            except Exception:
                pass  # Stage 3 narrows this and logs; a bad port just means try the next
            if port is not None:
                try:
                    port.close()
                except Exception:
                    pass
        self.missing.emit()

    def close(self):
        if self.keyer:
            try:
                self.keyer.host_close()
            except Exception:
                pass
        if self.port:
            try:
                self.port.close()
            except Exception:
                pass
        self.port = self.keyer = None
