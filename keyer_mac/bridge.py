"""XMLRPC bridge for logging software (masterplan Tech, module 5).

Runs a SimpleXMLRPCServer in its own thread and turns each call into a Qt
signal, so the UI/worker thread does the actual keying (no shared globals).
While the keyer is disconnected a call is dropped, not queued, and a `note`
signal says so (Spec feature 6).
"""

from __future__ import annotations

import threading
from xmlrpc.client import Fault
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

from PyQt6.QtCore import QObject, pyqtSignal

from keyer_mac.winkeyer import SPEED_MAX, SPEED_MIN


class _Quiet(SimpleXMLRPCRequestHandler):
    def log_message(self, *args):  # no stderr noise per request
        pass


class Bridge(QObject):
    send_string = pyqtSignal(str)
    send_blended = pyqtSignal(str)
    set_speed = pyqtSignal(int)
    tune_on = pyqtSignal()
    tune_off = pyqtSignal()
    clear_buffer = pyqtSignal()
    note = pyqtSignal(str)      # text for the Message box

    METHODS = ("k1elsendstring", "setspeed", "sendblended", "tuneon", "tuneoff", "clearbuffer")

    def __init__(self, host: str = "0.0.0.0", port: int = 8000, is_connected=lambda: True):
        super().__init__()
        self.host, self.port = host, port
        self._is_connected = is_connected
        self._server: SimpleXMLRPCServer | None = None
        self._thread: threading.Thread | None = None

    # -- lifecycle -------------------------------------------------------
    def start(self) -> bool:
        """Bind and serve. A bind failure (port in use) is reported via `note`
        and returns False; the app keeps running."""
        try:
            self._server = SimpleXMLRPCServer((self.host, self.port), requestHandler=_Quiet,
                                              logRequests=False, allow_none=True)
        except OSError as exc:
            self.note.emit(f"XMLRPC bridge off: port {self.port} unavailable ({exc.strerror or exc})")
            return False
        self.port = self._server.server_address[1]
        for name in self.METHODS:
            self._server.register_function(getattr(self, "_rpc_" + name), name)
        self._thread = threading.Thread(target=self._server.serve_forever, name="xmlrpc", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # -- rpc methods (run on the server thread) ----------------------------
    def _gate(self, what: str) -> bool:
        if self._is_connected():
            return True
        self.note.emit(f"XMLRPC {what} dropped: keyer disconnected")
        return False

    def _rpc_k1elsendstring(self, text):
        if self._gate("k1elsendstring"):
            self.send_string.emit(str(text))
        return True

    def _rpc_sendblended(self, text):
        if self._gate("sendblended"):
            self.send_blended.emit(str(text))
        return True

    def _rpc_setspeed(self, wpm):
        if not isinstance(wpm, int) or isinstance(wpm, bool) or not SPEED_MIN <= wpm <= SPEED_MAX or wpm % 2:
            raise Fault(1, f"speed must be an even integer {SPEED_MIN}-{SPEED_MAX}")
        if self._gate("setspeed"):
            self.set_speed.emit(wpm)
        return True

    def _rpc_tuneon(self):
        if self._gate("tuneon"):
            self.tune_on.emit()
        return True

    def _rpc_tuneoff(self):
        if self._gate("tuneoff"):
            self.tune_off.emit()
        return True

    def _rpc_clearbuffer(self):
        if self._gate("clearbuffer"):
            self.clear_buffer.emit()
        return True
