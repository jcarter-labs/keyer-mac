"""Task 1.2: the screenshot measurement is deterministic and finds the
numbers the masterplan quotes. Reads the two reference PNGs read-only."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import ui_fidelity_check  # noqa: E402
import ui_measure  # noqa: E402
from PyQt6.QtGui import QColor, QImage  # noqa: E402


def _synthetic(tmp_path):
    """200x120 gray window, one white box with a dark border, 10 px margins."""
    img = QImage(200, 120, QImage.Format.Format_RGB32)
    img.fill(QColor("#ededed"))
    for x in range(10, 190):
        for y in (20, 99):
            img.setPixelColor(x, y, QColor("#202020"))
    for y in range(20, 100):
        for x in (10, 189):
            img.setPixelColor(x, y, QColor("#202020"))
    for x in range(11, 189):
        for y in range(21, 99):
            img.setPixelColor(x, y, QColor("#ffffff"))
    path = tmp_path / "synthetic.png"
    img.save(str(path))
    return str(path)


def test_synthetic_window_and_box(tmp_path):
    m = ui_measure.measure(_synthetic(tmp_path), (2, 60), find_dropdown=False)
    assert m["window"]["width"] == 200
    box = m["text_boxes"][0]
    assert (box["x"], box["width"], box["height"]) == (10, 180, 80)
    assert box["fill"] == "#ffffff"
    assert m["margin_left"] == 10 and m["margin_right"] == 10


def test_running_screenshot_numbers():
    m = ui_measure.measure(str(ROOT / "keyer-mac-running.png"), (24, 300))
    assert m["window"]["width"] == 579
    assert (m["margin_left"], m["margin_right"]) == (15, 15)
    assert [b["height"] for b in m["text_boxes"]] == [112, 153]
    assert m["dropdown"]["width"] == 381
    assert m["button"]["width"] == 65
    assert m["message_rows"]["count"] == 6 and m["message_rows"]["pitch"] == 38


def test_targets_are_deterministic_and_match_brief(tmp_path):
    a = ui_fidelity_check.build_targets()
    b = ui_fidelity_check.build_targets()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    t = a["targets_1_1"]
    assert t["port_dropdown_width"] == 190          # half of 381, rounded
    assert t["message_row_count"] == 5
    assert (t["window_background"], t["field_fill"]) == ("#ededed", "#ffffff")
