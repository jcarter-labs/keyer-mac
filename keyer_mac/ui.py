"""Main window pieces (masterplan Tech, module 6). Stage 2 slice: a bare
window with only the Message box, running the scan countdown. No serial code
here; it talks to the Worker through signals.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from keyer_mac import winkeyer
from keyer_mac.worker import Worker

SCAN_SECONDS = 8
MISSING_TEXT = "Keyer missing: no WinKeyer detected. Plug it in; it will connect automatically."
WINDOW_BG = "#ededed"
FIELD_BG = "#ffffff"


class MessageBox(QPlainTextEdit):
    """Read-only, 3 lines. One status line updates in place; other text appends."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        font = QFont("Arial")
        font.setPointSize(16)
        self.setFont(font)
        self.setStyleSheet(f"background:{FIELD_BG};")
        self.setFixedHeight(3 * self.fontMetrics().lineSpacing() + 2 * self.frameWidth() + 12)

    def set_status(self, text: str) -> None:
        self.setPlainText(text)


class BareWindow(QWidget):
    """Message box + countdown. `lines` records every status shown (for tests)."""

    def __init__(self, worker: Worker | None = None):
        super().__init__()
        self.setWindowTitle("keyer-mac")
        self.setStyleSheet(f"QWidget{{background:{WINDOW_BG};font-family:Arial;}}")
        self.box = MessageBox()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.addWidget(self.box)
        self.resize(579, 120)
        self.lines: list[str] = []
        self.result: str | None = None      # "found" / "missing"
        self.remaining = SCAN_SECONDS
        self._scanning = False
        self._thread = QThread()
        self.worker = worker or Worker()
        self.worker.moveToThread(self._thread)
        self.worker.found.connect(self._on_found)
        self.worker.missing.connect(self._on_missing)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    def _show(self, text: str) -> None:
        self.lines.append(text)
        self.box.set_status(text)

    def start_scan(self, saved=None, manual=None,
                   mode_register=winkeyer.DEFAULT_MODE_REGISTER, speed=winkeyer.DEFAULT_SPEED) -> None:
        self.remaining, self._scanning, self.result = SCAN_SECONDS, True, None
        self._show(f"Scanning for keyer… {self.remaining}")
        self._timer.start()
        if not self._thread.isRunning():
            self._thread.start()
        self.worker.scan_requested.emit(saved, manual, mode_register, speed)

    def _tick(self) -> None:
        if self._scanning and self.remaining > 0:
            self.remaining -= 1
            self._show(f"Scanning for keyer… {self.remaining}")

    def _on_found(self, device: str, version: int, speed: int) -> None:
        self._scanning = False
        self._timer.stop()
        self.result = "found"
        self._show(f"Keyer found: WinKeyer v{winkeyer.format_version(version)} on {device}, {speed} WPM")

    def _on_missing(self) -> None:
        self._scanning = False
        self._timer.stop()
        self.result = "missing"
        self._show(MISSING_TEXT)

    def shutdown(self) -> None:
        self._timer.stop()
        self.worker.close()
        self._thread.quit()
        self._thread.wait(2000)

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
