"""Main window (masterplan Tech, module 6). No serial code: it talks to the
Worker (a QThread) and the Bridge only through signals.

Built feature by feature in Stage 4; widgets sit in the rows of the Spec's
screen list: 0 header, 1 Message box, 2 free-text label, 3 free-text box,
4-8 messages, 9 footer.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QMetaObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QGridLayout, QLabel, QLineEdit,
                             QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget)

import keyer_mac
from keyer_mac import config, winkeyer
from keyer_mac import ports as ports_mod
from keyer_mac.bridge import Bridge
from keyer_mac.settings import Settings
from keyer_mac.worker import Worker

WATCH_MS = 2000             # re-list ports this often while no keyer is connected
SCAN_SECONDS = 8
SCAN_PREFIX = "Scanning for keyer… "
DISCONNECTED_PREFIX = "Keyer disconnected. Scanning for keyer… "
MISSING_TEXT = "Keyer missing: no WinKeyer detected. Plug it in; it will connect automatically."
WINDOW_BG = "#ededed"
FIELD_BG = "#ffffff"
FONT_FAMILY = "Arial"
PT_ENTRY, PT_DROPDOWN, PT_LABEL, PT_FOOTER = 16, 14, 13, 11
MSG_BUTTON_WIDTH = 65       # measured from keyer-mac-running.png
PORT_BOX_WIDTH = 190        # half the 1.0 width (tools/ui_targets.json)
SETTINGS_UI = Path(__file__).resolve().parent / "settings.ui"


def arial(pt: int) -> QFont:
    font = QFont(FONT_FAMILY)
    font.setPointSize(pt)
    return font


def diff_edit(old: str, new: str) -> tuple[int, str]:
    """(backspaces, text to send) that turn `old` into `new` at the keyer:
    erase back to the common prefix, then send what follows it."""
    common = 0
    for a, b in zip(old, new):
        if a != b:
            break
        common += 1
    return len(old) - common, new[common:]


INFO_SUMMARY = "keyer-mac is an auto keyer written for the Mac to interface with a WinKeyer Mini via USB."
REPO = "jcarter-labs/keyer-mac"
REPO_URL = "https://github.com/jcarter-labs/keyer-mac"


def info_text(port: str | None, firmware: int | None, config_file, xmlrpc: str) -> str:
    """The Info dialog body: the summary first, then the facts."""
    fw = f"v{winkeyer.format_version(firmware)}" if firmware is not None else "not connected"
    methods = ", ".join(Bridge.METHODS)
    return "\n".join([
        INFO_SUMMARY,
        "",
        f"Version: {keyer_mac.__version__} ({keyer_mac.__build_date__})",
        f"Connected port: {port or 'none'}",
        f"WinKeyer firmware: {fw}",
        f"Config file: {config_file}",
        f"XMLRPC: {xmlrpc}",
        f"XMLRPC methods: {methods}",
        "",
        "Designed to work with the K1EL WinKeyer Mini.",
        "",
        "A Mac rewrite of PyWinKeyerSerial by Michael Bridak, K6GTE "
        "(https://github.com/mbridak/PyWinKeyerSerial). Licensed GPL-3.0-or-later: "
        "free software, with ABSOLUTELY NO WARRANTY; see the LICENSE file.",
        "",
        f"Repository: {REPO}",
        REPO_URL,
    ])


class InfoDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("keyer-mac info")
        self.setStyleSheet(f"QWidget{{background:{WINDOW_BG};font-family:{FONT_FAMILY};}}")
        layout = QVBoxLayout(self)
        self.body = QTextBrowser()
        self.body.setFont(arial(PT_LABEL))
        self.body.setStyleSheet(f"background:{FIELD_BG};")
        self.body.setOpenExternalLinks(True)
        self.body.setPlainText(text)
        layout.addWidget(self.body)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 420)


class MessageBox(QPlainTextEdit):
    """Read-only, 3 lines. The countdown updates one line in place; other
    status lines append (identical consecutive ones are not repeated); keyer
    echo appends to an echo line as it arrives."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFont(arial(PT_ENTRY))
        self.setStyleSheet(f"background:{FIELD_BG};")
        self.setFixedHeight(3 * self.fontMetrics().lineSpacing() + 2 * self.frameWidth() + 12)
        self.lines: list[str] = []
        self.kinds: list[str] = []

    def _render(self) -> None:
        self.setPlainText("\n".join(self.lines))
        self.moveCursor(QTextCursor.MoveOperation.End)

    def clear_all(self) -> None:
        self.lines, self.kinds = [], []
        self._render()

    def set_countdown(self, text: str) -> None:
        if self.kinds and self.kinds[-1] == "countdown":
            self.lines[-1] = text
        else:
            self.lines.append(text)
            self.kinds.append("countdown")
        self._render()

    def add_line(self, text: str) -> None:
        """Append a status line; a countdown line in progress is replaced."""
        if self.kinds and self.kinds[-1] == "countdown":
            self.lines[-1], self.kinds[-1] = text, "line"
        elif self.lines and self.kinds[-1] == "line" and self.lines[-1] == text:
            return
        else:
            self.lines.append(text)
            self.kinds.append("line")
        self._render()

    def add_echo(self, chars: str) -> None:
        if self.kinds and self.kinds[-1] == "echo":
            self.lines[-1] += chars
        else:
            self.lines.append(chars)
            self.kinds.append("echo")
        self._render()


class MainWindow(QWidget):
    sig_send_text = pyqtSignal(str)
    sig_backspace = pyqtSignal()
    sig_set_speed = pyqtSignal(int)
    sig_set_mode = pyqtSignal(int)

    def __init__(self, worker: Worker | None = None, cfg: dict | None = None,
                 list_ports=ports_mod.list_ports, start_bridge: bool = False,
                 bridge_host: str = "0.0.0.0", bridge_port: int = 8000):
        super().__init__()
        self.setWindowTitle("keyer-mac")
        self.setStyleSheet(f"QWidget{{background:{WINDOW_BG};font-family:{FONT_FAMILY};}}")
        self.cfg = cfg if cfg is not None else config.load()
        self._list_ports = list_ports
        self._seen_candidates: set[str] = set()
        self._connected = False
        self.lines: list[str] = []            # every status shown (for tests)
        self.result: str | None = None        # "found" / "missing"
        self.remaining = SCAN_SECONDS
        self._prefix = SCAN_PREFIX
        self._scanning = False
        self._old_text = ""

        grid = QGridLayout(self)
        grid.setContentsMargins(15, 15, 15, 15)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self.grid = grid

        # header row 0: "Message" label, Info, settings gear, port dropdown
        self.header_label = QLabel("Message")
        self.header_label.setFont(arial(PT_LABEL))
        grid.addWidget(self.header_label, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_button = QPushButton("Info")
        self.info_button.setFont(arial(PT_LABEL))
        self.info_button.clicked.connect(self.open_info)
        grid.addWidget(self.info_button, 0, 1)
        self.gear = QPushButton("⚙")
        self.gear.setFont(arial(PT_LABEL))
        self.gear.clicked.connect(self.open_settings)
        grid.addWidget(self.gear, 0, 2)
        self._firmware: int | None = None
        # port dropdown: editable; picking or typing a port tries it at once
        self.port_box = QComboBox()
        self.port_box.setEditable(True)
        self.port_box.setFont(arial(PT_DROPDOWN))
        self.port_box.setStyleSheet(f"background:{FIELD_BG};")
        self.port_box.setMinimumWidth(PORT_BOX_WIDTH)
        self.port_box.setMaximumWidth(PORT_BOX_WIDTH)
        grid.addWidget(self.port_box, 0, 3, 1, 3, Qt.AlignmentFlag.AlignRight)
        self.refresh_ports()
        self.port_box.activated.connect(lambda _i: self._port_chosen())
        self.port_box.lineEdit().editingFinished.connect(self._port_chosen)
        self.message = MessageBox()                       # row 1
        grid.addWidget(self.message, 1, 0, 1, 6)
        self.free_label = QLabel("Free text input")       # row 2
        self.free_label.setFont(arial(PT_LABEL))
        grid.addWidget(self.free_label, 2, 0, 1, 3, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # 4.3 speed: even values 6-34 WPM, right side of row 2
        self.speed_label = QLabel("Speed:")
        self.speed_label.setFont(arial(PT_LABEL))
        grid.addWidget(self.speed_label, 2, 3, 1, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.speed_box = QComboBox()
        self.speed_box.setFont(arial(PT_DROPDOWN))
        self.speed_box.setStyleSheet(f"background:{FIELD_BG};")
        for wpm in range(winkeyer.SPEED_MIN, winkeyer.SPEED_MAX + 1, 2):
            self.speed_box.addItem(str(wpm), wpm)
        self.speed_box.setCurrentIndex(self.speed_box.findData(self.cfg["speed"]))
        grid.addWidget(self.speed_box, 2, 5)
        self.speed_box.currentIndexChanged.connect(self._speed_chosen)
        self.free_text = QPlainTextEdit()                 # row 3
        self.free_text.setFont(arial(PT_ENTRY))
        self.free_text.setStyleSheet(f"background:{FIELD_BG};")
        self.free_text.setFixedHeight(3 * self.free_text.fontMetrics().lineSpacing()
                                      + 2 * self.free_text.frameWidth() + 12)
        grid.addWidget(self.free_text, 3, 0, 1, 6)
        self.free_text.textChanged.connect(self._free_text_changed)

        # 4.2 five canned messages, rows 4-8
        self.msg_fields: list[QLineEdit] = []
        self.msg_buttons: list[QPushButton] = []
        for i in range(5):
            field = QLineEdit(self.cfg.get(str(i + 1), ""))
            field.setFont(arial(PT_ENTRY))
            field.setStyleSheet(f"background:{FIELD_BG};")
            button = QPushButton(f"msg {i + 1}")
            button.setFont(arial(PT_LABEL))
            button.setFixedWidth(MSG_BUTTON_WIDTH)
            grid.addWidget(field, 4 + i, 0, 1, 5)
            grid.addWidget(button, 4 + i, 5)
            field.textChanged.connect(lambda _text, n=i: self._message_edited(n))
            button.clicked.connect(lambda _checked=False, n=i: self.send_message(n))
            self.msg_fields.append(field)
            self.msg_buttons.append(button)

        # 4.7 footer, row 9: build date left, version right
        self.date_label = QLabel(keyer_mac.__build_date__)
        self.date_label.setFont(arial(PT_FOOTER))
        grid.addWidget(self.date_label, 9, 0, 1, 3, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.version_label = QLabel(f"v{keyer_mac.__version__}")
        self.version_label.setFont(arial(PT_FOOTER))
        grid.addWidget(self.version_label, 9, 3, 1, 3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.resize(579, 220)

        self._thread = QThread()
        self.worker = worker or Worker()
        self.worker.moveToThread(self._thread)
        self.sig_send_text.connect(self.worker.send_text)
        self.sig_backspace.connect(self.worker.backspace)
        self.sig_set_speed.connect(self.worker.set_speed)
        self.sig_set_mode.connect(self.worker.set_mode)
        self.worker.found.connect(self._on_found)
        self.worker.missing.connect(self._on_missing)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.echoed.connect(self.message.add_echo)
        self.worker.note.connect(self._on_note)
        self.worker.diagnostic.connect(self._on_diagnostic)
        self.worker.retry_scheduled.connect(self._on_retry_scheduled)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        # 4.5 XMLRPC bridge: calls become signals into the worker / this window
        self.bridge = Bridge(bridge_host, bridge_port, is_connected=lambda: self._connected)
        self.bridge.send_string.connect(self.worker.send_text)
        self.bridge.send_blended.connect(self.worker.send_blended)
        self.bridge.set_speed.connect(self._bridge_set_speed)
        self.bridge.tune_on.connect(self.worker.tune_on)
        self.bridge.tune_off.connect(self.worker.tune_off)
        self.bridge.clear_buffer.connect(self.worker.clear_buffer)
        self.bridge.note.connect(self._on_note)
        if start_bridge:
            self.bridge.start()
        self._watch = QTimer(self)
        self._watch.setInterval(WATCH_MS)
        self._watch.timeout.connect(self._watch_ports)

    # -- port dropdown and hot-plug watch ----------------------------------------
    def refresh_ports(self) -> None:
        """List every port (virtual ones too, with their description as a
        tooltip), keeping the current text."""
        current = self.port_box.currentText()
        self.port_box.blockSignals(True)
        self.port_box.clear()
        for p in self._list_ports():
            self.port_box.addItem(p.device)
            self.port_box.setItemData(self.port_box.count() - 1, p.description, Qt.ItemDataRole.ToolTipRole)
        self.port_box.setCurrentText(current or self.cfg.get("device", ""))
        self.port_box.blockSignals(False)

    def _port_chosen(self) -> None:
        device = self.port_box.currentText().strip()
        if device and device != getattr(self.worker, "device", None):
            self.start_scan(manual=device)

    def _watch_ports(self) -> None:
        """While no keyer is connected, notice a newly enumerated WK-mini and
        try it now instead of waiting out the retry backoff."""
        if self._connected:
            return
        ports = self._list_ports()
        candidates = {p.device for p in ports if ports_mod.is_winkeyer_candidate(p)}
        new = candidates - self._seen_candidates
        self._seen_candidates = candidates
        self.refresh_ports()
        if new:
            self.start_scan()

    # -- status and countdown ------------------------------------------------
    def _record(self, text: str) -> None:
        self.lines.append(text)

    def _start_countdown(self, prefix: str) -> None:
        self._prefix, self.remaining, self._scanning, self.result = prefix, SCAN_SECONDS, True, None
        self._show_countdown()
        self._timer.start()

    def _show_countdown(self) -> None:
        text = f"{self._prefix}{self.remaining}"
        self.message.set_countdown(text)
        self._record(text)

    def start_scan(self, saved=None, manual=None) -> None:
        self._connected = False
        self._seen_candidates = {p.device for p in self._list_ports() if ports_mod.is_winkeyer_candidate(p)}
        self._watch.start()
        self.message.clear_all()
        self._start_countdown(SCAN_PREFIX)
        if not self._thread.isRunning():
            self._thread.start()
        self.worker.scan_requested.emit(
            saved if saved is not None else (self.cfg.get("device") or None), manual,
            config.mode_register_int(self.cfg), self.cfg["speed"])

    def _tick(self) -> None:
        if self._scanning and self.remaining > 0:
            self.remaining -= 1
            self._show_countdown()

    def _on_found(self, device: str, version: int, speed: int) -> None:
        self._scanning = False
        self._timer.stop()
        self._connected = True
        self._firmware = version
        self.result = "found"
        self.port_box.blockSignals(True)
        self.port_box.setCurrentText(device)
        self.port_box.blockSignals(False)
        self.message.clear_all()
        text = f"Keyer found: WinKeyer v{winkeyer.format_version(version)} on {device}, {speed} WPM"
        self.message.add_line(text)
        self._record(text)
        self.cfg["device"] = device          # saved only after a successful handshake
        config.save(self.cfg)

    def _on_missing(self) -> None:
        self._scanning = False
        self._timer.stop()
        self.result = "missing"
        self.message.add_line(MISSING_TEXT)
        self._record(MISSING_TEXT)

    def _on_disconnected(self) -> None:
        self._connected = False
        self._firmware = None
        self.message.add_line("Keyer disconnected.")
        self._start_countdown(DISCONNECTED_PREFIX)

    def _on_diagnostic(self, text: str) -> None:
        """A failure and its reason, time-stamped, so it can be diagnosed by use."""
        line = f"{datetime.now():%H:%M:%S} {text}"
        self.message.add_line(line)
        self._record(line)

    def _on_retry_scheduled(self, delay_s: float) -> None:
        self._on_diagnostic(f"Retrying in {int(delay_s)} s")

    def _on_note(self, text: str) -> None:
        self.message.add_line(text)
        self._record(text)

    # -- 4.1 free-text sending -----------------------------------------------
    def _free_text_changed(self) -> None:
        new = self.free_text.toPlainText()
        backspaces, text = diff_edit(self._old_text, new)
        self._old_text = new
        for _ in range(backspaces):
            self.sig_backspace.emit()
        if text:
            self.sig_send_text.emit(text)

    # -- 4.6 Info ---------------------------------------------------------------------
    def info_body(self) -> str:
        bound = self.bridge.is_running()
        xmlrpc = f"{self.bridge.host}:{self.bridge.port}" if bound else "off (port unavailable)"
        return info_text(getattr(self.worker, "device", None) if self._connected else None,
                         self._firmware, config.config_path(), xmlrpc)

    def open_info(self) -> None:
        InfoDialog(self.info_body(), self).exec()

    # -- 4.5 XMLRPC ----------------------------------------------------------------
    def _bridge_set_speed(self, wpm: int) -> None:
        self.show_speed(wpm)              # dropdown follows, saved
        self.sig_set_speed.emit(wpm)      # and the keyer gets it

    # -- 4.4 settings dialog -----------------------------------------------------
    def open_settings(self) -> None:
        """Edit the keyer mode register. Save writes it to the keyer and the
        JSON; Cancel changes nothing."""
        pref = {"mode_register": self.cfg["mode_register"]}
        dialog = Settings(SETTINGS_UI, pref, self)
        if dialog.exec():
            self.apply_mode_register(pref["mode_register"])

    def apply_mode_register(self, bits: str) -> None:
        self.cfg["mode_register"] = bits
        config.save(self.cfg)
        self.sig_set_mode.emit(int(bits, 2))

    # -- 4.3 speed -------------------------------------------------------------
    def _speed_chosen(self, _index: int) -> None:
        """A value picked in the dropdown is sent at once and saved."""
        wpm = self.speed_box.currentData()
        self.cfg["speed"] = wpm
        config.save(self.cfg)
        self.sig_set_speed.emit(wpm)

    def show_speed(self, wpm: int) -> None:
        """Show a speed that was set elsewhere (XMLRPC): no second send."""
        index = self.speed_box.findData(wpm)
        if index >= 0:
            self.speed_box.blockSignals(True)
            self.speed_box.setCurrentIndex(index)
            self.speed_box.blockSignals(False)
            self.cfg["speed"] = wpm
            config.save(self.cfg)

    # -- 4.2 canned messages -------------------------------------------------
    def _message_edited(self, index: int) -> None:
        """Every edit is saved at once (whole-file write)."""
        self.cfg[str(index + 1)] = self.msg_fields[index].text()
        config.save(self.cfg)

    def send_message(self, index: int) -> None:
        text = self.msg_fields[index].text()
        if text:
            self.sig_send_text.emit(text)

    # -- lifecycle ---------------------------------------------------------------
    def shutdown(self) -> None:
        self.bridge.stop()
        self._timer.stop()
        self._watch.stop()
        if self._thread.isRunning():
            QMetaObject.invokeMethod(self.worker, "close", Qt.ConnectionType.BlockingQueuedConnection)
            self._thread.quit()
            self._thread.wait(2000)
        else:
            self.worker.close()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)


BareWindow = MainWindow   # Stage 2 name, kept until the callers are updated
