"""Pixel measurement of a reference screenshot (Task 1.2).

Pure functions on a QImage so they can be unit-tested on synthetic images.
Measures what a screenshot actually shows, in image pixels (1 px = 1 pt for
the two reference screenshots; the 579 px window width matches main.ui).

Method: a box border is a row where dark pixels span most of the window
width; a faint field/dropdown outline is a row where mid-light gray pixels
form a long run. Everything else is derived from those rows and columns.
"""

from PyQt6.QtGui import QImage

DARK = 0xC8      # luminance below this counts as a box border pixel
FAINT_LO = 0xE0  # faint outlines (dropdown, message fields) sit in this band
FAINT_HI = 0xF8


def lum(image: QImage, x: int, y: int) -> int:
    c = image.pixelColor(x, y)
    return (c.red() + c.green() + c.blue()) // 3


def hex_at(image: QImage, x: int, y: int) -> str:
    return image.pixelColor(x, y).name()


def longest_run(flags: list[bool]) -> tuple[int, int] | None:
    """(start, end) inclusive of the longest True run, or None."""
    best, start = None, None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if best is None or i - start > best[1] - best[0] + 1:
                best = (start, i - 1)
            start = None
    return best


def window_body(image: QImage, probe: tuple[int, int]) -> tuple[int, int, int, int]:
    """(left, right, top, bottom) of the window body: the most common
    (first, last) x of background-coloured pixels over all rows, and the
    first/last row that has that pair. Inside the body every row starts and
    ends with the margin, so that pair wins by a wide margin; the title bar,
    window shadow and desktop behind it do not match and drop out."""
    from collections import Counter

    bg = hex_at(image, *probe)
    pairs, rows_of = Counter(), {}
    for y in range(image.height()):
        xs = [x for x in range(image.width()) if hex_at(image, x, y) == bg]
        if xs:
            pairs[(xs[0], xs[-1])] += 1
            rows_of.setdefault((xs[0], xs[-1]), []).append(y)
    pair = pairs.most_common(1)[0][0]
    rows = rows_of[pair]
    return pair[0], pair[1], rows[0], rows[-1]


def border_bands(image: QImage, left: int, right: int, top: int, bottom: int, frac: float = 0.8) -> list[tuple[int, int]]:
    """(first_row, last_row) of each band of rows where dark pixels span at
    least `frac` of the window width."""
    need = frac * (right - left + 1)
    rows = [y for y in range(top, bottom + 1)
            if sum(1 for x in range(left, right + 1) if lum(image, x, y) < DARK) >= need]
    bands, start = [], None
    for i, y in enumerate(rows):
        if start is None:
            start = y
        if i + 1 == len(rows) or rows[i + 1] != y + 1:
            bands.append((start, y))
            start = None
    return bands


def faint_rows(image: QImage, x0: int, x1: int, y0: int, y1: int, min_run: int) -> list[tuple[int, int, int]]:
    """(y, x_start, x_end) of faint outline runs at least `min_run` long."""
    out = []
    for y in range(y0, y1):
        flags = [FAINT_LO <= lum(image, x, y) <= FAINT_HI for x in range(x0, x1 + 1)]
        run = longest_run(flags)
        if run and run[1] - run[0] + 1 >= min_run:
            out.append((y, x0 + run[0], x0 + run[1]))
    return out


def group_pairs(rows: list[int]) -> list[tuple[int, int]]:
    """Pair consecutive border rows into (top, bottom)."""
    return [(rows[i], rows[i + 1]) for i in range(0, len(rows) - 1, 2)]


def measure(path: str, probe: tuple[int, int], find_dropdown: bool = True) -> dict:
    image = QImage(path)
    if image.isNull():
        raise FileNotFoundError(path)
    left, right, top, bottom = window_body(image, probe)
    result = {
        "image": path,
        "image_size": [image.width(), image.height()],
        "window": {"left": left, "right": right, "width": right - left + 1,
                   "body_top": top, "body_bottom": bottom,
                   "background": hex_at(image, *probe)},
        "text_boxes": [],
    }
    # thin bands are box borders; a thick band is a title bar and is skipped
    lines = [b[0] for b in border_bands(image, left, right, top, bottom) if b[1] - b[0] <= 3]
    big_boxes, small_boxes = [], []
    for t, b in group_pairs(lines):
        (big_boxes if b - t + 1 >= 60 else small_boxes).append((t, b))
    for t, b in big_boxes:
        mid = (t + b) // 2
        xs = [x for x in range(left, right + 1) if lum(image, x, mid) < DARK]
        x0, x1 = (min(xs), max(xs)) if xs else (left, right)
        result["text_boxes"].append({
            "top": t, "bottom": b, "height": b - t + 1, "x": x0,
            "width": x1 - x0 + 1, "fill": hex_at(image, (x0 + x1) // 2, mid)})
    if big_boxes:
        first = result["text_boxes"][0]
        result["margin_left"] = first["x"] - left
        result["margin_right"] = right - (first["x"] + first["width"] - 1)
        # skip the title-bar edge (full-width) by capping the run length
        rows0 = [r for r in faint_rows(image, left, right, top + 8, big_boxes[0][0] - 1, min_run=60)
                 if r[2] - r[1] + 1 < 0.9 * (right - left + 1)]
        if rows0 and find_dropdown:
            y, a0, a1 = rows0[0]
            # outer width: the straight top edge stops at the rounded corners,
            # so read the vertical edges at mid-height instead
            y2 = rows0[1][0] if len(rows0) > 1 else y + 25
            mid = (y + y2) // 2
            ex = [x for x in range(a0 - 12, a1 + 13)
                  if FAINT_LO <= lum(image, x, mid) <= FAINT_HI]
            e0, e1 = (min(ex), max(ex)) if ex else (a0, a1)
            result["dropdown"] = {"top": y, "height": y2 - y + 1, "x": e0, "width": e1 - e0 + 1}
    # message fields: dark outlines (win-ui) or faint outlines (running)
    starts = [t for t, _ in small_boxes]
    heights = [b - t + 1 for t, b in small_boxes]
    if not starts and big_boxes:
        rows = faint_rows(image, left + 10, right - 90, big_boxes[-1][1] + 1, bottom, min_run=200)
        tops = [r[0] for r in rows]
        starts = tops[0::2]
        heights = [tops[i + 1] - tops[i] + 1 for i in range(0, len(tops) - 1, 2)]
    if starts:
        # button: non-background pixels in the right-hand 90 px of the first field row
        mid = starts[0] + heights[0] // 2
        bg = result["window"]["background"]
        flags = [hex_at(image, x, mid) != bg for x in range(right - 90, right + 1)]
        run = longest_run(flags)  # the field outline is a thin run; the button is the long one
        if run:
            result["button"] = {"x": right - 90 + run[0], "width": run[1] - run[0] + 1}
    if len(starts) > 1:
        result["message_rows"] = {
            "count": len(starts), "first_top": starts[0],
            "pitch": starts[1] - starts[0], "field_height": heights[0]}
    return result
