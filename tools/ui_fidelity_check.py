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
       python3 tools/ui_fidelity_check.py --targets [ui_targets.json]   (Task 1.2)
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


def build_targets() -> dict:
    """Task 1.2: numeric 1.1 layout targets, measured from the two reference
    screenshots (tools/ui_measure.py) with the 1.1 brief's changes applied.
    Deterministic: the same inputs always give the same JSON."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ui_measure

    root = Path(__file__).resolve().parent.parent
    run = ui_measure.measure(str(root / "keyer-mac-running.png"), (24, 300))
    win = ui_measure.measure(str(root / "keyer-win-ui.png"), (5, 300), find_dropdown=False)
    rows = run["message_rows"]
    return {
        "tolerance_px": 2,
        "measured": {"keyer-mac-running.png": run, "keyer-win-ui.png": win},
        "targets_1_1": {
            "window_width": run["window"]["width"],
            "margin_left": run["margin_left"],
            "margin_right": run["margin_right"],
            "port_dropdown_width": round(run["dropdown"]["width"] / 2),
            "port_dropdown_height": run["dropdown"]["height"],
            "message_box_lines": 3,
            "free_text_box_lines": 3,
            "message_row_count": 5,
            "message_row_gap": rows["pitch"] - rows["field_height"],
            "msg_button_width": run["button"]["width"],
            "msg_button_right_edge_flush_to_margin": True,
            "window_background": win["window"]["background"],
            "field_fill": win["text_boxes"][0]["fill"],
            "font_family": "Arial",
            "font_pt": {"entry_and_display": 16, "dropdowns": 14,
                        "labels_and_buttons": 13, "footer": 11},
            "box_height_rule": "lines * QFontMetrics.lineSpacing() + 2 * frame; "
                               "1.0 baseline (13 pt): message box %d px, free-text box %d px"
                               % (run["text_boxes"][0]["height"], run["text_boxes"][1]["height"]),
        },
    }


def write_targets(path: str) -> dict:
    targets = build_targets()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(targets, f, indent=2, sort_keys=True)
        f.write("\n")
    return targets


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--targets":
        out = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parent / "ui_targets.json")
        t = write_targets(out)["targets_1_1"]
        print(json.dumps(t, indent=2, sort_keys=True))
        print(f"\nWrote {out}")
        return 0
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
