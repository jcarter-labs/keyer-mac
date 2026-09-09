#!/usr/bin/env python3
"""
keyer-mac — a macOS port of Michael Bridak's (K6GTE) PyWinKeyerSerial.
https://github.com/mbridak/PyWinKeyerSerial

This program talks to the WinKeyerUSB and WinKeyerSerial devices by K1EL.
It sends what you type to the keyer, and sends presaved messages when you press the
appropriate button.

The first time you run this program it creates a file '.keyer-mac.json'
in the root of your home directory. This file is used to store the default serial
device and the presaved messages.

When you update the presaved message fields they are resaved automatically.

The speed is initially set by polling the speed pot.

The speed pot should work to change the code speed on the fly.

This is where I realized that not all K1EL keyers have a speedpot on them....

You really should have gotten the one with the speedpot.....
"""

# >>> a=12
# >>> bin(a)
# '0b1100'
# >>> f"{a:b}"
# '1100'
# >>> f"{a:08b}"
# '00001100'
# >>> c = '00001100'
# >>> c
# '00001100'
# >>> int(c,2)
# 12

# disable_paddle_watchdog
# paddle_echo_back
# key_mode 00=B 01=A 10=U 11=bug
# paddle_swap
# serial_echoback
# autospace
# ct_spacing

# pylint: disable=no-name-in-module, c-extension-no-member, global-statement, bare-except

import sys
import os
import json
import time

from pathlib import Path
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler
import logging


import serial
from serial.tools.list_ports import comports

from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QWidget

# from PyQt6.QtCore import Qt
from PyQt6 import uic
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import QThread

from keyer_mac.settings import Settings

logging.basicConfig(level=logging.WARNING)

MESSAGE = ""

HEARTBEAT_INTERVAL_S = 60


def _is_real_serial_port(serialport) -> bool:
    """
    Best-effort filter distinguishing a real USB-serial device from a
    macOS virtual/compatibility port (e.g. /dev/cu.Bluetooth-Incoming-Port,
    /dev/cu.debug-console) reported by `comports()`. See
    deviation-log.md #7 for the incident this exists to prevent.

    Primary signal: pyserial's `vid` (USB vendor id). It is a structural
    fact populated by the OS/driver for genuine USB serial adapters and
    is `None` for non-USB virtual ports — confirmed on this machine:
    `comports(include_links=True)` returned exactly one entry with a
    non-None vid/pid (`/dev/cu.usbserial-8340`, description "USB
    Serial"); every virtual entry (`Bluetooth-Incoming-Port`,
    `debug-console`, and a paired Bluetooth accessory port) had vid None
    and description "n/a".

    Fallback (vid unavailable, e.g. a backend/OS combination that
    doesn't populate it): treat a missing/"n/a" description as the
    virtual signal instead. Deliberately not pattern-matching on
    `/dev/cu.*` name fragments — those are macOS-specific and don't
    generalize to Linux (`/dev/ttyUSB0`) or Windows (`COM3`) naming,
    while vid/description are reported the same way by pyserial across
    platforms.
    """
    if getattr(serialport, "vid", None) is not None:
        return True
    description = (getattr(serialport, "description", "") or "").strip().lower()
    return description not in ("", "n/a")


def config_path() -> str:
    """
    Resolve the dotfile config path. KEYER_MAC_CONFIG_PATH overrides the
    default so tests never touch the operator's real $HOME (Constitution
    rule 10) — production default is unaffected.
    """
    override = os.environ.get("KEYER_MAC_CONFIG_PATH")
    if override:
        return override
    return os.path.expanduser("~/.keyer-mac.json")


class RequestHandler(SimpleXMLRPCRequestHandler):
    """Doc String"""

    rpc_paths = ("/RPC2",)


class RPCThread(QThread):
    """Doc String"""

    def __init__(self, parent=None):
        QThread.__init__(self, parent)
        self.server = None
        self._stop_requested = False

    def stop(self):
        """Signal the server loop to exit and return; safe to call before the server starts."""
        self._stop_requested = True
        if self.server is not None:
            # serve_forever() polls every 0.5 s, so this returns within that window.
            self.server.shutdown()

    def run(self):
        """Doc String"""
        # sleep a little bit to make sure QApplication is running.
        self.sleep(1)
        if self._stop_requested:
            return
        print("--- starting server…")
        try:
            with SimpleXMLRPCServer(("0.0.0.0", 8000), allow_none=True) as self.server:
                self.server.register_function(k1elsendstring)
                self.server.register_function(setspeed)
                self.server.register_function(sendblended)
                self.server.register_function(tuneon)
                self.server.register_function(tuneoff)
                self.server.register_function(clearbuffer)
                self.server.register_introspection_functions()
                self.server.serve_forever()
        except OSError as err:
            # Source leaves this bind unguarded, so any bind failure (port
            # already in use — another instance, a leftover process, an
            # unrelated service) crashes the whole app: an unhandled
            # exception escaping a QThread.run() override makes PyQt6
            # print it and abort() the process, keyer included. Logging
            # and returning instead means a port conflict costs only the
            # XMLRPC bridge for that run, not the running app.
            self.server = None
            logging.error(
                "RPCThread: could not start XMLRPC server on 0.0.0.0:8000 (%s) — "
                "the keyer will still work, XMLRPC-driven logging software won't "
                "be able to reach it this run.",
                err,
            )


class RPCWidget(QWidget):
    """Doc String"""

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.thread = RPCThread(self)
        self.thread.start()


def k1elsendstring(sss):
    """Doc String"""
    global MESSAGE
    MESSAGE += f"{sss}"


class WinKeyer(QtWidgets.QMainWindow):
    """
    The main class
    """

    version = 0
    device = ""
    oldtext = ""
    port = None
    initialpot = False

    def __init__(self, *args, **kwargs):
        """
        connects the widgets to their callbacks.
        queries for existing serial ports.
        loads in saved defaults.
        """
        # A fresh dict per instance — source declared this as a mutable class
        # attribute, which is harmless for the single instance a real run
        # creates but corrupts state across instances (Task 5's tests caught
        # this: see deviation-log.md #4).
        self.settings_dict = {"device": "", "1": "", "2": "", "3": "", "4": "", "5": "", "6": ""}
        self.working_path = Path(os.path.dirname(os.path.abspath(__file__)))

        data_path = self.working_path / "main.ui"
        super().__init__(*args, **kwargs)
        uic.loadUi(data_path, self)
        self.sendmsg1_button.clicked.connect(self.sendmsg1)
        self.sendmsg2_button.clicked.connect(self.sendmsg2)
        self.sendmsg3_button.clicked.connect(self.sendmsg3)
        self.sendmsg4_button.clicked.connect(self.sendmsg4)
        self.sendmsg5_button.clicked.connect(self.sendmsg5)
        self.sendmsg6_button.clicked.connect(self.sendmsg6)
        self.settings_gear.clicked.connect(self.edit_configuration_settings)
        self.inputbox.textChanged.connect(self.handle_text_change)
        # Speed-control arbitration (deviation-log.md #6): a WK-mini with no
        # physical pot still emits pot-status bytes off its floating ADC
        # line, which would otherwise permanently overwrite the spinbox
        # every 100ms poll. Track each source's own last value and only
        # act on a genuine change from that source, so a stale/repeated
        # pot echo can't reclobber a manual speed change, while a real pot
        # movement (if a unit has one) still takes control as source intends.
        self._last_pot_speed = None
        self._last_manual_speed = None
        self._suppress_spinbox_signal = False
        self.spinBox_speed.valueChanged.connect(self.spinboxspeed)
        self.spinBox_speed.setValue(20)
        self._shutting_down = False
        self._write_timeout_logged = False
        self.last_tx_time = 0.0
        # Reconnect backoff/settle state (deviation-log.md #8): getwaiting()'s
        # error path used to call host_init() unconditionally on every
        # failure, up to every 100ms (timer2's period) — a failing reopen
        # that itself fails to get a version response re-arms the same
        # 100ms poll, which can then hit the same error again immediately.
        # These fields throttle that path without touching a first/explicit
        # host_init() call (main() at startup, change_serial() from the UI).
        self._reconnect_attempt = 0
        self._next_reconnect_time = 0.0
        self._reconnect_backoff_base_s = 1.0
        self._reconnect_backoff_max_s = 30.0
        self._is_reconnect = False
        self._first_open_settle_s = 0.5
        self._reconnect_settle_s = 1.5
        self.timer2 = QTimer()
        self.timer2.timeout.connect(self.getwaiting)
        # Auto-selection default when there is nothing better to go on yet
        # (no saved config, or the saved device turns out to be missing —
        # see loadsaved()). Source picked whichever port comports()
        # happened to enumerate *last*, arbitrary and OS-order-dependent;
        # that could — and on this machine's real incident, did — be a
        # macOS virtual/compatibility port with no WinKeyer behind it
        # (deviation-log.md #7). last_real_device tracks the same
        # "last one wins" rule but only among candidates that look like
        # actual USB serial hardware (_is_real_serial_port), so a virtual
        # port enumerated after the real one no longer clobbers it.
        # last_any_device preserves the exact old fallback ("last
        # enumerated, whatever it is") for the case where nothing in the
        # list looks like real hardware — still better to offer *some*
        # default than none, unchanged from source there.
        last_real_device = ""
        last_any_device = ""
        for serialport in comports(include_links=True):
            self.comboBox_device.addItem(serialport.device)
            index = self.comboBox_device.findText(serialport.device)
            self.comboBox_device.setItemData(index, serialport.description)
            last_any_device = serialport.device
            if _is_real_serial_port(serialport):
                last_real_device = serialport.device
        self.device = last_real_device or last_any_device
        self.settings_dict["device"] = self.device
        # loadsaved() below overwrites self.device from whatever was
        # persisted last run — including a *virtual* device, deliberately
        # (see loadsaved()'s docstring). This is kept as the fallback for
        # the separate, unambiguous case where there is truly nothing
        # saved to honor (no "device" key, or an empty one).
        self._auto_default_device = self.device
        self.comboBox_device.setEditable(True)
        self.loadsaved()
        self.comboBox_device.currentIndexChanged.connect(self.change_serial)
        self.comboBox_device.lineEdit().editingFinished.connect(self.change_serial)

    def change_serial(self):
        """
        The serial device was changed via the onscreen widget.
        """
        self.settings_dict["device"] = self.comboBox_device.currentText()
        self.savestuff()
        self.device = self.settings_dict.get("device")
        self.host_init()
        if self.port:
            self.setmode()

    def loadsaved(self):
        """
        load saved default device and messages if they exist.
        otherwise write some sane defaults as a json text file in the users home directory.

        Deliberately does NOT second-guess a saved device that looks
        virtual (deviation-log.md #7) — a saved "device" value, whatever
        it is, is trusted verbatim exactly as source always did, because
        it may reflect a deliberate manual choice (the combobox stays
        editable specifically so a user can pick any enumerated port,
        virtual ones included) and there is no way to tell that apart
        from a stale bad default after the fact. What *is* hardened is
        the narrower, unambiguous case of nothing saved to honor at all
        (no "device" key, or an empty one) — that falls back to
        `self._auto_default_device`, the real-hardware-preferring pick
        computed in __init__, instead of an empty string.
        """
        path = config_path()
        if os.path.exists(path):
            with open(path, "rt", encoding="utf-8") as file_handle:
                self.settings_dict = json.loads(file_handle.read())
        else:
            with open(path, "wt", encoding="utf-8") as file_handle:
                file_handle.write(json.dumps(self.settings_dict))
        self.device = self.settings_dict.get("device") or self._auto_default_device
        self.settings_dict["device"] = self.device
        self.msg1.setText(self.settings_dict.get("1"))
        self.msg2.setText(self.settings_dict.get("2"))
        self.msg3.setText(self.settings_dict.get("3"))
        self.msg4.setText(self.settings_dict.get("4"))
        self.msg5.setText(self.settings_dict.get("5"))
        self.msg6.setText(self.settings_dict.get("6"))
        # connect the change events to resave messages
        self.msg1.textChanged.connect(self.savestuff)
        self.msg2.textChanged.connect(self.savestuff)
        self.msg3.textChanged.connect(self.savestuff)
        self.msg4.textChanged.connect(self.savestuff)
        self.msg5.textChanged.connect(self.savestuff)
        self.msg6.textChanged.connect(self.savestuff)

    def savestuff(self):
        """
        save state as a json file in the home directory
        """
        self.settings_dict["1"] = self.msg1.text()
        self.settings_dict["2"] = self.msg2.text()
        self.settings_dict["3"] = self.msg3.text()
        self.settings_dict["4"] = self.msg4.text()
        self.settings_dict["5"] = self.msg5.text()
        self.settings_dict["6"] = self.msg6.text()
        with open(config_path(), "wt", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(self.settings_dict))
        self.setmode()

    def host_init(self, is_reconnect=False):
        """
        Opens the serial port and sets its parameters.

        is_reconnect: True when this call originates from getwaiting()'s
        error-recovery path rather than a first/explicit open (startup,
        or the user picking a device in the combo box). host_open() uses
        it to allow more settle time before judging the keyer unresponsive
        (deviation-log.md #8) — a reconnect may follow a mid-transaction
        error, unlike a cold boot.
        """
        self._is_reconnect = is_reconnect
        self.outputbox.clear()
        self.comboBox_device.blockSignals(True)
        index = self.comboBox_device.findText(self.device)
        if index >= 0:
            self.comboBox_device.setCurrentIndex(index)
        else:
            self.comboBox_device.setCurrentText(self.device)
        self.comboBox_device.blockSignals(False)
        try:
            if self.port:
                self.port.close()
            self.port = serial.Serial()
            self.port.port = self.device
            self.port.baudrate = 1200
            self.port.bytesize = serial.EIGHTBITS
            self.port.parity = serial.PARITY_NONE
            self.port.stopbits = serial.STOPBITS_TWO
            self.port.dsrdtr = True
            self.port.rtscts = False
            self.port.timeout = 0
            self.port.write_timeout = 1  # prevent writes from blocking forever if the device stops responding
            self.port.open()
            if not self.port.is_open:
                msg = f"Unable to open serial port: {self.device}"
                logging.warning(msg)
                self.outputbox.insertPlainText(msg)
                self._register_reconnect_failure()
                return
        except serial.serialutil.SerialException:
            msg = f"Unable to open serial port: {self.device}"
            logging.warning(msg)
            self.outputbox.insertPlainText(msg)
            self.port = False
            self._register_reconnect_failure()
            return
        self.host_open()

    def host_open(self):
        """
        Sends the open command to winkeyer so it will start listening to us.
        """
        self.host_close()
        time.sleep(1)  # wait for the keyer to reset.
        command = b"\x00\x02"
        self._port_write(command)
        # A reconnect (vs. a cold boot) may follow a read/write error that
        # left the WinKeyer or the USB-serial bridge mid-transaction; give
        # it more time to settle before judging it unresponsive. HYPOTHESIS,
        # not confirmed against real hardware in this worktree (task rule:
        # no live serial port here) — see deviation-log.md #8.
        settle_s = self._reconnect_settle_s if self._is_reconnect else self._first_open_settle_s
        time.sleep(settle_s)
        self.version = self.port.read(255)
        if self.version == b"":  # No version... Maybe the wrong serial port was chosen.
            msg = f"{self.device} is open but WinKeyer is not responding"
            # This message previously only ever reached the on-screen output
            # box, invisible to any terminal/log-based diagnostic — logged
            # here too so it's observable without watching the GUI.
            logging.warning(msg)
            self.outputbox.clear()
            self.outputbox.insertPlainText(msg)
            self._register_reconnect_failure()
        else:
            self._register_reconnect_success()
        self.timer2.start(100)

        # Send POTSET to configure speed pot range: min=5 WPM, range=50 WPM (5-55 WPM).
        # Without this, the keyer uses its own default MIN_WPM which may differ from
        # what this host assumes when decoding pot speed bytes (raw - 123 = raw - 0x80 + 5).
        command = b"\x05\x05\x32\x00"
        self._port_write(command)

        command = b"\x07"  # have the winkeyer return the pot speed setting
        self._port_write(command)

    def _register_reconnect_failure(self):
        """
        Record a failed (re)connect attempt and grow the backoff window
        before getwaiting() is allowed to trigger another one automatically
        (deviation-log.md #8). Exponential, capped at
        _reconnect_backoff_max_s, so a device that stays gone gets polled
        less and less often rather than every 100ms — but never stops
        entirely, since there's no UI affordance for the operator to force
        a retry other than re-picking the device in the combo box (which
        calls host_init() directly and bypasses this gate anyway).
        """
        self._reconnect_attempt += 1
        backoff = min(
            self._reconnect_backoff_base_s * (2 ** (self._reconnect_attempt - 1)),
            self._reconnect_backoff_max_s,
        )
        self._next_reconnect_time = time.time() + backoff
        logging.warning(
            "host_init: reconnect attempt #%d failed for %s, backing off %.1fs before the next automatic attempt",
            self._reconnect_attempt,
            self.device,
            backoff,
        )

    def _register_reconnect_success(self):
        """Clear backoff state once the WinKeyer responds again."""
        if self._reconnect_attempt:
            logging.info(
                "host_init: %s responded again after %d failed attempt(s)",
                self.device,
                self._reconnect_attempt,
            )
        self._reconnect_attempt = 0
        self._next_reconnect_time = 0.0

    def host_close(self):
        """
        Sends the close command to winkeyer
        """
        if hasattr(self.port, "write"):
            command = b"\x00\x03"
            self._port_write(command)

    def _port_write(self, data):
        try:
            self.port.write(data)
        except serial.SerialTimeoutException:
            # A timed-out write is expected when the device is gone (e.g. during shutdown).
            # Log only once per failure episode to avoid flooding the log.
            if not self._write_timeout_logged:
                logging.warning("_port_write: write timeout, device may be disconnected")
                self._write_timeout_logged = True
            return
        if self._write_timeout_logged:
            logging.info("_port_write: device is responding again")
            self._write_timeout_logged = False
        self.last_tx_time = time.time()

    def setspeed(self, speed):
        """
        Sets winkeyer speed. I believe valid speeds are from 5 to brainmelt
        """
        if hasattr(self.port, "write"):
            command = chr(2) + chr(int(speed))
            self._port_write(command.encode())
            self._suppress_spinbox_signal = True
            self.spinBox_speed.setValue(int(speed))
            self._suppress_spinbox_signal = False

    def potspeed(self, speed):
        """
        The pot speed value is the 6 LSB of the returned byte.
        It has the 2 MSB of the byte set to 10.

        Only acts on a genuine change from the pot's own last-reported
        value — a WK-mini with no physical pot still emits status bytes
        off its floating ADC line, and without this check that stale,
        repeated reading would permanently overwrite any speed set from
        the spinbox or XMLRPC (see deviation-log.md #6).
        """
        wpm = speed - 123
        if wpm == self._last_pot_speed:
            return
        self._last_pot_speed = wpm
        self.setspeed(wpm)

    def spinboxspeed(self):
        """
        User changed the speed value in the spinbox — or this fired
        because setspeed() just updated the displayed value itself (pot
        or XMLRPC driven); only treat it as a real manual change, and
        re-send, when it's not our own echo and the value actually moved
        (see deviation-log.md #6).
        """
        if self._suppress_spinbox_signal:
            return
        wpm = self.spinBox_speed.value()
        if wpm == self._last_manual_speed:
            return
        self._last_manual_speed = wpm
        self.setspeed(wpm)

    def setmode(self):
        """
        Basically tells the device 'Hey, well be expecting you to
        transform letters into boop-ity boop stuff.'
        """
        bin_register = self.settings_dict.get("mode_register", "11001110")
        int_register = int(bin_register, 2)

        if hasattr(self.port, "write"):
            command = b"\x0e" + int_register.to_bytes()
            self._port_write(command)

    def sendblended(self, msg):
        """
        a way to glue together two characters to send a prosign.
        """
        if hasattr(self.port, "write"):
            command = b"\x1b" + msg.upper().encode()
            self._port_write(command)

    def send(self, msg):
        """
        Basic string in, Morse out of the device.
        """
        if hasattr(self.port, "write"):
            command = msg.upper().encode()
            self._port_write(command)

    def send_backspace(self):
        """
        Erases a character from the end of the winkeyer buffer if it has not been sent already.
        """
        if hasattr(self.port, "write"):
            command = b"\x08"
            self._port_write(command)

    def tuneon(self):
        """
        Keydown and hold it.
        """
        if hasattr(self.port, "write"):
            command = b"\x0b\x01"
            self._port_write(command)

    def tuneoff(self):
        """
        Stop the keydown
        """
        if hasattr(self.port, "write"):
            command = b"\x0b\x00"
            self._port_write(command)

    def clearbuffer(self):
        """
        Stop the keydown
        """
        if hasattr(self.port, "write"):
            command = b"\x0a"
            self._port_write(command)

    def sendmsg1(self):
        """
        This and the following just pull text from the fields next to the button and sends it.
        """
        if hasattr(self.port, "write"):
            local_message = self.msg1.text()
            self._port_write(local_message.upper().encode())

    def sendmsg2(self):
        """
        This and the following just pull text from the fields next to the button and sends it.
        """
        if hasattr(self.port, "write"):
            local_message = self.msg2.text()
            self._port_write(local_message.upper().encode())

    def sendmsg3(self):
        """
        This and the following just pull text from the fields next to the button and sends it.
        """
        if hasattr(self.port, "write"):
            local_message = self.msg3.text()
            self._port_write(local_message.upper().encode())

    def sendmsg4(self):
        """
        This and the following just pull text from the fields next to the button and sends it.
        """
        if hasattr(self.port, "write"):
            local_message = self.msg4.text()
            self._port_write(local_message.upper().encode())

    def sendmsg5(self):
        """
        This and the following just pull text from the fields next to the button and sends it.
        """
        if hasattr(self.port, "write"):
            local_message = self.msg5.text()
            self._port_write(local_message.upper().encode())

    def sendmsg6(self):
        """
        This and the following just pull text from the fields next to the button and sends it.
        """
        if hasattr(self.port, "write"):
            local_message = self.msg6.text()
            self._port_write(local_message.upper().encode())

    def handle_text_change(self):
        """
        This is a poorly handled function where it sends text you type in the big box to the keyer.
        But hey, you get what you pay for. If you can do better then have at it.
        Oh and send a pull request when your done.
        """
        newtext = self.inputbox.toPlainText()
        if len(newtext) < len(self.oldtext):
            self.send_backspace()
            self.oldtext = newtext
            return
        self.send(newtext[len(self.oldtext) :])
        self.oldtext = newtext

    def getwaiting(self):
        """
        Checks to see the keyer has data to send to us.
        Could be a status change.
        Could be the user has twisted that turney bit thingy with the knob on it.
        It could also be an echo of the last character it has sent or is sending.
        """
        if self._shutting_down:
            return
        # A previous automatic reconnect (below) can leave self.port as the
        # bool `False` (host_init()'s open() failed) rather than restarting
        # timer2 — source's bare `except:` then caught the resulting
        # AttributeError on `self.port.in_waiting` and called host_init()
        # again, every 100ms, with no backoff: a tight reconnect-storm on a
        # port that's actually gone. Handled explicitly here instead of via
        # exception (deviation-log.md #8).
        if not self.port or not getattr(self.port, "is_open", False):
            self._attempt_reconnect()
            return
        try:
            if time.time() - self.last_tx_time >= HEARTBEAT_INTERVAL_S:
                if hasattr(self.port, "write") and self.port.is_open:
                    self._port_write(b"\x15")
            if self.port.in_waiting:
                byte = self.port.read(1)
                if not byte:
                    # in_waiting said data was available but read(1) came back
                    # empty — a benign non-blocking-read race (timeout=0), not
                    # a device fault. Source's bare except would have treated
                    # the resulting byte[0] IndexError as "unplugged" and
                    # reconnected; just skip this poll instead.
                    return
                if (byte[0] & b"\xc0"[0]) == b"\xc0"[0]:  # Status Change
                    pass
                elif (byte[0] & b"\xc0"[0]) == b"\x80"[0]:  # speed pot change
                    self.potspeed(byte[0])
                else:  # process echoback character
                    if 0x20 <= byte[0] <= 0x7E:
                        # print(byte.decode(), end="", flush=True)
                        self.outputbox.insertPlainText(f"{byte.decode()}")
        except serial.SerialException as err:
            # Narrowed from source's bare `except:` (deviation-log.md #2/#8):
            # pyserial's POSIX backend raises SerialException (or a subclass —
            # PortNotOpenError, SerialTimeoutException; both subclass it, and
            # it subclasses OSError itself) for every genuine serial-layer
            # fault, including "device reports readiness to read but returned
            # no data" on a real disconnect. A bug elsewhere in this method
            # (a real AttributeError/IndexError/etc.) now propagates instead
            # of being silently misdiagnosed as "someone unplugged the
            # keyer" and masked by a reconnect.
            if not self._shutting_down:
                logging.warning("getwaiting: serial error on %s (%s)", self.device, err)
                self._attempt_reconnect()

    def _attempt_reconnect(self):
        """
        Gate automatic reconnects behind the backoff window set by the last
        failure (deviation-log.md #8), so a still-failing device is retried
        with growing spacing instead of every 100ms (timer2's period).
        """
        if self._shutting_down:
            return
        if time.time() < self._next_reconnect_time:
            return
        self.host_init(is_reconnect=True)

    def checkmessage(self):
        """
        This is so hackish, it's a bit embarassing.
        This should be handled with slots and signals.
        But.... It works.
        """
        global MESSAGE
        sss = MESSAGE
        MESSAGE = ""
        if sss and hasattr(self.port, "write"):
            self._port_write(sss.upper().encode())

    def edit_configuration_settings(self) -> None:
        """
        Configuration Settings was clicked

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        data_path = self.working_path / "settings.ui"
        self.configuration_dialog = Settings(data_path, self.settings_dict)
        self.configuration_dialog.show()
        self.configuration_dialog.accepted.connect(self.edit_configuration_return)

    def edit_configuration_return(self) -> None:
        """
        Returns here when configuration dialog closed with okay.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """

        self.configuration_dialog.save_changes()
        self.savestuff()

    def _shutdown(self):
        """Stop serial I/O and close the port, then quit the application."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self.timer2.stop()
        try:
            self.host_close()
        except Exception:
            pass
        try:
            if self.port and hasattr(self.port, "close"):
                self.port.close()
        except Exception:
            pass
        try:
            # rpcwidget may not exist if shutdown fires before module-level setup completes.
            rpcwidget.thread.stop()
            rpcwidget.thread.wait(1000)  # wait at most 1 second for the RPC thread to exit
        except Exception:
            pass
        app.quit()

    def closeEvent(self, a0):
        """Send host close command to WinKeyer before exiting."""
        self._shutdown()
        if a0 is not None:
            a0.accept()


import signal

# These start as None so importing this module (as tests do, to reach the
# WinKeyer/Settings classes) never creates a QApplication, opens the real
# serial port, or binds the real XMLRPC server — only main() does that, and
# main() only ever runs via `python3 -m keyer_mac` (Constitution rule 10).
# Source ran all of this at module level, since it was written as a script,
# never meant to be imported; ported behavior is unchanged, only *when* it
# runs has moved.
app = None
keyer = None
rpcwidget = None
timer = None


def setspeed(speed) -> None:
    """doc"""
    keyer.setspeed(speed)


def tuneon() -> None:
    """doc"""
    keyer.tuneon()


def tuneoff() -> None:
    """doc"""
    keyer.tuneoff()


def clearbuffer() -> None:
    """doc"""
    keyer.clearbuffer()


def sendblended(msg) -> None:
    """doc"""
    keyer.sendblended(msg)


def _handle_sigint(_signum, _frame):
    keyer._shutdown()


def main():
    """Main entry"""
    global app, keyer, rpcwidget, timer

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    # instance()-or-construct is a test-only seam: a real run always has no
    # existing QApplication, so this is identical to source's plain
    # QApplication(sys.argv). It only matters when pytest imports this module
    # more than once per process — Qt raises on a second bare constructor call.
    keyer = WinKeyer()
    keyer.show()

    # Register before host_init so Ctrl+C during startup is handled cleanly.
    signal.signal(signal.SIGINT, _handle_sigint)
    signal.signal(signal.SIGTERM, _handle_sigint)

    keyer.host_init()
    if keyer.port:
        keyer.setmode()
    rpcwidget = RPCWidget()
    timer = QTimer()
    timer.timeout.connect(keyer.checkmessage)  # Do not do this.

    timer.start(250)
    app.exec()


if __name__ == "__main__":
    main()
