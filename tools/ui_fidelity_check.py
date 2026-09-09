#!/usr/bin/env python3
"""Task 6 polish-pass measurement tool. Per the UI Fidelity rule, a layout
claimed to match a reference needs a numeric, re-runnable measurement, not
eyeballing — this is that measurement, run against the actual rendered
widget geometry rather than the .ui source XML, so it reflects what Qt
really lays out (including maximumSize/font-driven sizing).

Launches WinKeyer headless (QT_QPA_PLATFORM=offscreen), grabs each named
widget's geometry (position + size, relative to the main window) and each
label's alignment flags, and saves a real rendered screenshot via
QWidget.grab() for visual comparison against keyer-win-ui.png. No hardware
or config-file writes needed beyond an isolated temp path.

Usage: python3 tools/ui_fidelity_check.py [output.png]
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KEYER_MAC_CONFIG_PATH", "/tmp/keyer_mac_ui_fidelity_check.json")

from PyQt6.QtWidgets import QApplication, QLabel

from keyer_mac.__main__ import WinKeyer

WIDGET_NAMES = [
    "label", "comboBox_device", "settings_gear", "outputbox",
    "label_2", "label_3", "spinBox_speed", "inputbox",
    "msg1", "sendmsg1_button", "msg2", "sendmsg2_button",
    "msg3", "sendmsg3_button", "msg4", "sendmsg4_button",
    "msg5", "sendmsg5_button", "msg6", "sendmsg6_button",
]

ALIGNMENT_FLAG_NAMES = {
    0x0001: "AlignLeft", 0x0002: "AlignRight", 0x0004: "AlignHCenter",
    0x0008: "AlignJustify", 0x0020: "AlignTop", 0x0040: "AlignBottom",
    0x0080: "AlignVCenter", 0x0002: "AlignTrailing",
}


def describe_alignment(flags: int) -> str:
    names = [name for bit, name in ALIGNMENT_FLAG_NAMES.items() if flags & bit]
    return "|".join(dict.fromkeys(names)) or "(none)"


def main() -> int:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/keyer_mac_ui_fidelity.png"

    app = QApplication.instance() or QApplication([])
    win = WinKeyer()
    win.show()  # geometry() is all zeros until the window is shown and laid out
    for _ in range(5):
        app.processEvents()

    report = []
    for name in WIDGET_NAMES:
        widget = getattr(win, name, None)
        if widget is None:
            report.append({"name": name, "error": "widget not found"})
            continue
        geo = widget.geometry()
        entry = {
            "name": name,
            "x": geo.x(), "y": geo.y(),
            "width": geo.width(), "height": geo.height(),
        }
        if isinstance(widget, QLabel):
            entry["alignment"] = describe_alignment(int(widget.alignment()))
            entry["text"] = widget.text()
        report.append(entry)

    print(f"Window size: {win.size().width()}x{win.size().height()}\n")
    print(f"{'widget':<20} {'x':>5} {'y':>5} {'w':>5} {'h':>5}  extra")
    for e in report:
        if "error" in e:
            print(f"{e['name']:<20} ERROR: {e['error']}")
            continue
        extra = ""
        if "alignment" in e:
            extra = f"align={e['alignment']} text={e['text']!r}"
        print(f"{e['name']:<20} {e['x']:>5} {e['y']:>5} {e['width']:>5} {e['height']:>5}  {extra}")

    pixmap = win.grab()
    pixmap.save(out_path)
    print(f"\nSaved rendered screenshot to {out_path}")

    report_path = out_path.rsplit(".", 1)[0] + ".json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Saved geometry report to {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
