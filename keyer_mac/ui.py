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
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget)

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
PORT_BOX_HEIGHT = 26
MESSAGE_ROW_GAP = 17        # measured from keyer-mac-running.png
WINDOW_WIDTH = 579
BORDER = "#b6b6b6"
STYLE = f"""
QWidget {{ background:{WINDOW_BG}; font-family:{FONT_FAMILY}; }}
QLabel {{ background:transparent; }}
QPlainTextEdit, QLineEdit {{ background:{FIELD_BG}; border:1px solid {BORDER}; border-radius:3px; }}
QComboBox {{ background:{FIELD_BG}; border:1px solid {BORDER}; border-radius:4px; padding:0px 6px; }}
QComboBox QLineEdit {{ border:none; }}
QComboBox QAbstractItemView {{ background:{FIELD_BG}; }}
QPushButton {{ background:#f7f7f7; border:1px solid {BORDER}; border-radius:5px; padding:3px 8px; }}
QPushButton:pressed {{ background:#dcdcdc; }}
QTextBrowser {{ background:{FIELD_BG}; }}
"""
SETTINGS_UI = Path(__file__).resolve().parent / "settings.ui"


def arial(pt: int) -> QFont:
    font = QFont(FONT_FAMILY)
    font.setPointSize(pt)
    return font


def box_height_for_lines(box: QPlainTextEdit, lines: int) -> int:
    """Widget height whose viewport shows exactly `lines` text lines."""
    return (lines * box.fontMetrics().lineSpacing() + 2 * int(box.document().documentMargin())
            + 2 * box.frameWidth())


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
        self.setStyleSheet(STYLE)
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
    """Read-only, 3 lines. Entries are status lines, time-stamped diagnostics,
    keyer echo and one live countdown. The countdown (if any) is always the
    last line and updates in place; everything else is inserted above it.
    A diagnostic that repeats the previous one replaces it (new time stamp)
    instead of piling up; identical consecutive status lines are not repeated."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFont(arial(PT_ENTRY))
        self.setFixedHeight(box_height_for_lines(self, 3))
        self.entries: list[list] = []        # [kind, key, text]

    @property
    def lines(self) -> list[str]:
        return [e[2] for e in self.entries]

    @property
    def kinds(self) -> list[str]:
        return [e[0] for e in self.entries]

    def _render(self) -> None:
        self.setPlainText("\n".join(self.lines))
        self.moveCursor(QTextCursor.MoveOperation.End)

    def _insert_index(self) -> int:
        """Where a non-countdown entry goes: above the countdown, if there is one."""
        if self.entries and self.entries[-1][0] == "countdown":
            return len(self.entries) - 1
        return len(self.entries)

    def clear_all(self) -> None:
        self.entries = []
        self._render()

    def clear_countdown(self) -> None:
        self.entries = [e for e in self.entries if e[0] != "countdown"]
        self._render()

    def set_countdown(self, text: str) -> None:
        self.entries = [e for e in self.entries if e[0] != "countdown"]
        self.entries.append(["countdown", None, text])
        self._render()

    def add_line(self, text: str) -> None:
        i = self._insert_index()
        if i and self.entries[i - 1][0] == "line" and self.entries[i - 1][2] == text:
            return
        self.entries.insert(i, ["line", None, text])
        self._render()

    def add_diag(self, text: str, key: str) -> None:
        i = self._insert_index()
        if i and self.entries[i - 1][0] == "diag" and self.entries[i - 1][1] == key:
            self.entries[i - 1][2] = text
        else:
            self.entries.insert(i, ["diag", key, text])
        self._render()

    def add_echo(self, chars: str) -> None:
        i = self._insert_index()
        if i and self.entries[i - 1][0] == "echo":
            self.entries[i - 1][2] += chars
        else:
            self.entries.insert(i, ["echo", None, chars])
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
        self.setStyleSheet(STYLE)
        self.cfg = cfg if cfg is not None else config.load()
        self._list_ports = list_ports
        self._seen_candidates: set[str] = set()
        self._connected = False
        self.lines: list[str] = []            # every status shown (for tests)
        self.result: str | None = None        # "found" / "missing"
        self.remaining = SCAN_SECONDS
        self._prefix = SCAN_PREFIX
        self._scanning = False
        self._missing_shown = False
        self._old_text = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(15, 15, 15, 15)
        root.setSpacing(4)
        self.root = root
        al_left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        al_right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        # row 0: "Message" label, Info, settings gear ... port dropdown (right)
        header = QHBoxLayout()
        header.setSpacing(10)
        self.header_label = QLabel("Message")
        self.header_label.setFont(arial(PT_LABEL))
        self.info_button = QPushButton("Info")
        self.info_button.setFont(arial(PT_LABEL))
        self.info_button.clicked.connect(self.open_info)
        self.gear = QPushButton("⚙")
        self.gear.setFont(arial(PT_LABEL))
        self.gear.clicked.connect(self.open_settings)
        self._firmware: int | None = None
        # port dropdown: editable; picking or typing a port tries it at once
        self.port_box = QComboBox()
        self.port_box.setEditable(True)
        self.port_box.setFont(arial(PT_DROPDOWN))
        self.port_box.setFixedSize(PORT_BOX_WIDTH, PORT_BOX_HEIGHT)
        for widget in (self.header_label, self.info_button, self.gear):
            header.addWidget(widget)
        header.addStretch(1)
        header.addWidget(self.port_box)
        root.addLayout(header)
        self.refresh_ports()
        self.port_box.activated.connect(lambda _i: self._port_chosen())
        self.port_box.lineEdit().editingFinished.connect(self._port_chosen)

        # row 1: Message box
        self.message = MessageBox()
        root.addWidget(self.message)

        # row 2: "Free text input" (left); "Speed:" + speed dropdown (right)
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.free_label = QLabel("Free text input")
        self.free_label.setFont(arial(PT_LABEL))
        self.speed_label = QLabel("Speed:")
        self.speed_label.setFont(arial(PT_LABEL))
        self.speed_box = QComboBox()
        self.speed_box.setFont(arial(PT_DROPDOWN))
        for wpm in range(winkeyer.SPEED_MIN, winkeyer.SPEED_MAX + 1, 2):
            self.speed_box.addItem(str(wpm), wpm)
        self.speed_box.setCurrentIndex(self.speed_box.findData(self.cfg["speed"]))
        self.speed_box.currentIndexChanged.connect(self._speed_chosen)
        row2.addWidget(self.free_label, 0, al_left)
        row2.addStretch(1)
        row2.addWidget(self.speed_label, 0, al_right)
        row2.addWidget(self.speed_box)
        root.addLayout(row2)

        # row 3: free-text box
        self.free_text = QPlainTextEdit()
        self.free_text.setFont(arial(PT_ENTRY))
        self.free_text.setFixedHeight(box_height_for_lines(self.free_text, 3))
        self.free_text.textChanged.connect(self._free_text_changed)
        root.addWidget(self.free_text)

        # rows 4-8: five canned messages, 17 px apart (measured)
        msg_grid = QGridLayout()
        msg_grid.setHorizontalSpacing(10)
        msg_grid.setVerticalSpacing(MESSAGE_ROW_GAP)
        msg_grid.setColumnStretch(0, 1)
        self.msg_fields: list[QLineEdit] = []
        self.msg_buttons: list[QPushButton] = []
        for i in range(5):
            field = QLineEdit(self.cfg.get(str(i + 1), ""))
            field.setFont(arial(PT_ENTRY))
            button = QPushButton(f"msg {i + 1}")
            button.setFont(arial(PT_LABEL))
            button.setFixedWidth(MSG_BUTTON_WIDTH)
            msg_grid.addWidget(field, i, 0)
            msg_grid.addWidget(button, i, 1)
            field.textChanged.connect(lambda _text, n=i: self._message_edited(n))
            button.clicked.connect(lambda _checked=False, n=i: self.send_message(n))
            self.msg_fields.append(field)
            self.msg_buttons.append(button)
        root.addLayout(msg_grid)

        # row 9: footer, build date left, version right
        footer = QHBoxLayout()
        self.date_label = QLabel(keyer_mac.__build_date__)
        self.date_label.setFont(arial(PT_FOOTER))
        self.version_label = QLabel(f"v{keyer_mac.__version__}")
        self.version_label.setFont(arial(PT_FOOTER))
        footer.addWidget(self.date_label, 0, al_left)
        footer.addStretch(1)
        footer.addWidget(self.version_label, 0, al_right)
        root.addLayout(footer)
        self.setFixedWidth(WINDOW_WIDTH)
        self.adjustSize()

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
        try it now instead of waiting out the 8 s between automatic attempts."""
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

    def _start_countdown(self, prefix: str, seconds: int = SCAN_SECONDS) -> None:
        self._prefix, self.remaining, self._scanning = prefix, seconds, True
        self._show_countdown()
        self._timer.start()

    def _show_countdown(self) -> None:
        # at 0 the attempt is running; say so instead of sitting on "0"
        text = f"{self._prefix}{self.remaining if self.remaining > 0 else 'connecting'}"
        self.message.set_countdown(text)
        self._record(text)

    def start_scan(self, saved=None, manual=None) -> None:
        self._connected = False
        self._seen_candidates = {p.device for p in self._list_ports() if ports_mod.is_winkeyer_candidate(p)}
        self._watch.start()
        self.message.clear_all()
        self.result, self._missing_shown = None, False
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
        self._missing_shown = False
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
        self.result = "missing"
        if not self._missing_shown:
            self._missing_shown = True
            self.message.add_line(MISSING_TEXT)
            self._record(MISSING_TEXT)

    def _on_disconnected(self) -> None:
        self._connected = False
        self._firmware = None
        self.message.add_line("Keyer disconnected.")
        self.result, self._missing_shown = None, False
        self._start_countdown(DISCONNECTED_PREFIX)

    def _on_diagnostic(self, text: str) -> None:
        """A failure and its reason, time-stamped, so it can be diagnosed by use."""
        line = f"{datetime.now():%H:%M:%S} {text}"
        self.message.add_diag(line, key=text)
        self._record(line)

    def _on_retry_scheduled(self, delay_s: float) -> None:
        """An attempt failed: the same 8 s scan countdown starts over, so the
        number always means "seconds until the next try"."""
        self._start_countdown(SCAN_PREFIX, int(delay_s))

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
