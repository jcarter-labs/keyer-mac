#!/usr/bin/env python3
"""UI fidelity: numeric, re-runnable layout measurement (Standing Bar).

  python3 tools/ui_fidelity_check.py --targets [ui_targets.json]
      Task 1.2: measure the two reference screenshots (tools/ui_measure.py)
      and write the numeric 1.1 targets.
  python3 tools/ui_fidelity_check.py [out.png]
      Task 5.1: launch the real MainWindow offscreen, measure its actual
      widget geometry, fonts and colours against tools/ui_targets.json, print
      PASS/FAIL per item, save a rendered screenshot, exit 1 on any FAIL.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KEYER_MAC_CONFIG_PATH", str(Path(tempfile.gettempdir()) / "keyer_mac_ui_fidelity.json"))

TARGETS_PATH = Path(__file__).resolve().parent / "ui_targets.json"


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
                        "labels_and_buttons": 13, "gear_glyph": 20, "footer": 11},
            "header_gap": 10,
            "control_height": 26,
            "speed_dropdown_min_width": 60,
            "box_height_rule": "the viewport shows exactly 3 text lines "
                               "(viewport height // QFontMetrics.lineSpacing() == 3); "
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


def check_window(targets: dict, out_png: str) -> list[tuple[str, bool, str]]:
    """Measure the real window; return (item, passed, detail) rows."""
    from PyQt6.QtWidgets import QApplication, QLabel

    import keyer_mac
    from keyer_mac import config
    from keyer_mac.ui import (FONT_FAMILY, PT_DROPDOWN, PT_ENTRY, PT_FOOTER, PT_GEAR, PT_LABEL,
                              MainWindow)

    t = targets["targets_1_1"]
    tol = targets["tolerance_px"]
    app = QApplication.instance() or QApplication([])
    win = MainWindow(cfg=config.defaults(), list_ports=lambda: [])
    win.show()
    for _ in range(5):
        app.processEvents()
    rows = []

    def row(item, ok, detail):
        rows.append((item, bool(ok), detail))

    def near(item, got, want):
        row(item, abs(got - want) <= tol, f"got {got}, want {want} +/-{tol}")

    def right_of(widget):
        return win.width() - (widget.geometry().x() + widget.geometry().width())

    near("window width", win.width(), t["window_width"])
    near("left margin (message box x)", win.message.geometry().x(), t["margin_left"])
    near("right margin (message box right gap)", right_of(win.message), t["margin_right"])
    near("port dropdown width", win.port_box.width(), t["port_dropdown_width"])
    near("port dropdown height", win.port_box.height(), t["port_dropdown_height"])
    near("port dropdown flush to right margin", right_of(win.port_box), t["margin_right"])
    for name, box in (("message box", win.message), ("free-text box", win.free_text)):
        text_h = box.viewport().height() - 2 * int(box.document().documentMargin())
        ls = box.fontMetrics().lineSpacing()
        row(f"{name} shows exactly 3 lines", text_h == 3 * ls, f"text area {text_h} px / line {ls} px = {text_h / ls:.2f}")
    row("5 message rows", len(win.msg_fields) == t["message_row_count"] == 5, f"{len(win.msg_fields)} fields")
    tops = [f.geometry().y() for f in win.msg_fields]
    gaps = [tops[i + 1] - (tops[i] + win.msg_fields[i].height()) for i in range(4)]
    row("message row gap", all(abs(g - t["message_row_gap"]) <= tol for g in gaps), f"gaps {gaps}, want {t['message_row_gap']} +/-{tol}")
    near("msg button width", win.msg_buttons[0].width(), t["msg_button_width"])
    near("msg button right edge flush to margin", right_of(win.msg_buttons[0]), t["margin_right"])
    row("buttons share a row with their field", all(
        abs(f.geometry().y() + f.height() // 2 - b.geometry().y() - b.height() // 2) <= tol
        for f, b in zip(win.msg_fields, win.msg_buttons)), "centres within tolerance")

    # order and alignment, top to bottom / left to right
    ys = [win.header_label.y(), win.message.y(), win.free_label.y(), win.free_text.y(),
          win.msg_fields[0].y(), win.msg_fields[4].y(), win.date_label.y()]
    row("rows run top to bottom", ys == sorted(ys) and len(set(ys)) == len(ys), f"y {ys}")
    xs = [win.header_label.x(), win.info_button.x(), win.gear.x(), win.port_box.x()]
    row("header: Message, Info, gear, port dropdown, left to right", xs == sorted(xs) and len(set(xs)) == 4, f"x {xs}")
    row("speed on the free-text label's row, right side",
        win.speed_box.y() <= win.free_label.y() + win.free_label.height()
        and win.speed_box.x() > win.window().width() // 2 and win.speed_label.x() < win.speed_box.x(),
        f"label x {win.speed_label.x()}, box x {win.speed_box.x()}")
    row("footer: date left, version right",
        win.date_label.x() < win.width() // 3 and win.version_label.geometry().right() > 2 * win.width() // 3,
        f"date x {win.date_label.x()}, version right {win.version_label.geometry().right()}")
    row("free-text label left of the speed label; speed label touches its dropdown",
        win.free_label.x() < win.speed_label.x() < win.speed_box.x()
        and 0 <= win.speed_box.x() - (win.speed_label.x() + win.speed_label.width()) <= 12,
        f"label x {win.free_label.x()}, speed label {win.speed_label.x()}..{win.speed_label.x() + win.speed_label.width()}, box x {win.speed_box.x()}")

    # header grouping: Info | gear | port box, equal gaps, equal heights
    gap_a = win.gear.x() - (win.info_button.x() + win.info_button.width())
    gap_b = win.port_box.x() - (win.gear.x() + win.gear.width())
    row("Info-gear and gear-port gaps equal the header gap",
        abs(gap_a - t["header_gap"]) <= tol and abs(gap_b - t["header_gap"]) <= tol, f"gaps {gap_a}, {gap_b}, want {t['header_gap']}")
    heights = [w.height() for w in (win.info_button, win.gear, win.port_box, win.speed_box)]
    row("Info, gear and both dropdowns share one height", all(abs(h - t["control_height"]) <= tol for h in heights), f"{heights}")
    row("speed dropdown wide enough for its popup", win.speed_box.width() >= t["speed_dropdown_min_width"], f"{win.speed_box.width()} px")

    # fonts
    def font_ok(widget, pt):
        f = widget.font()
        return f.family() == FONT_FAMILY and f.pointSize() == pt
    groups = {
        f"{PT_ENTRY} pt entry/display": [win.message, win.free_text, *win.msg_fields],
        f"{PT_DROPDOWN} pt dropdowns": [win.speed_box, win.port_box],
        f"{PT_LABEL} pt labels/buttons": [win.header_label, win.free_label, win.speed_label, win.info_button,
                                          *win.msg_buttons],
        f"{PT_GEAR} pt gear glyph": [win.gear],
        f"{PT_FOOTER} pt footer": [win.date_label, win.version_label],
    }
    for name, widgets in groups.items():
        bad = [type(w).__name__ for w in widgets if not font_ok(w, int(name.split()[0]))]
        row(f"Arial {name}", not bad, f"wrong: {bad}" if bad else f"{len(widgets)} widgets")

    # colours from the rendered window
    image = win.grab().toImage()
    img_bg = image.pixelColor(3, 3).name()
    mb = win.message.geometry()
    img_field = image.pixelColor(mb.x() + mb.width() - 8, mb.y() + mb.height() - 8).name()
    row("window background", img_bg == t["window_background"], f"{img_bg} vs {t['window_background']}")
    row("field fill", img_field == t["field_fill"], f"{img_field} vs {t['field_fill']}")

    win.grab().save(out_png)
    win.shutdown()
    rows.append(("screenshot saved", True, out_png))
    return rows


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--targets":
        out = sys.argv[2] if len(sys.argv) > 2 else str(TARGETS_PATH)
        t = write_targets(out)["targets_1_1"]
        print(json.dumps(t, indent=2, sort_keys=True))
        print(f"\nWrote {out}")
        return 0
    out_png = sys.argv[1] if len(sys.argv) > 1 else "/tmp/keyer_mac_ui_fidelity.png"
    targets = json.loads(TARGETS_PATH.read_text())
    rows = check_window(targets, out_png)
    width = max(len(r[0]) for r in rows)
    for item, ok, detail in rows:
        print(f"{'PASS' if ok else 'FAIL'}  {item:<{width}}  {detail}")
    failed = [r for r in rows if not r[1]]
    print(f"\n{'PASS' if not failed else 'FAIL'}: {len(rows) - len(failed)}/{len(rows)} items")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
