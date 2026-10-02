"""Settings file (masterplan Tech, module 1): ~/.keyer-mac.json.

Flat JSON, written whole-file on every change. Keys: `device`, `speed`,
`1`-`5` (canned messages), `mode_register` (8-character bit string, as in
1.0). Unknown keys (including a leftover `6`) are ignored on load and
dropped on the next save. A missing file gives defaults; an unreadable one
gives defaults and is kept as `<name>.bad` for inspection.

KEYER_MAC_CONFIG_PATH redirects the file (tests, tools).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from keyer_mac.winkeyer import DEFAULT_SPEED, SPEED_MAX, SPEED_MIN

MESSAGE_KEYS = ("1", "2", "3", "4", "5")
DEFAULT_MODE_BITS = "11001110"


def config_path() -> Path:
    override = os.environ.get("KEYER_MAC_CONFIG_PATH")
    return Path(override) if override else Path(os.path.expanduser("~/.keyer-mac.json"))


def defaults() -> dict:
    cfg = {"device": "", "speed": DEFAULT_SPEED, "mode_register": DEFAULT_MODE_BITS}
    cfg.update({k: "" for k in MESSAGE_KEYS})
    return cfg


def _valid_speed(value) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and SPEED_MIN <= value <= SPEED_MAX and value % 2 == 0)


def _valid_mode(value) -> bool:
    return isinstance(value, str) and len(value) == 8 and set(value) <= {"0", "1"}


def clean(raw: object) -> dict:
    """Merge a loaded object over the defaults, keeping only valid known keys."""
    cfg = defaults()
    if not isinstance(raw, dict):
        return cfg
    if isinstance(raw.get("device"), str):
        cfg["device"] = raw["device"]
    if _valid_speed(raw.get("speed")):
        cfg["speed"] = raw["speed"]
    if _valid_mode(raw.get("mode_register")):
        cfg["mode_register"] = raw["mode_register"]
    for key in MESSAGE_KEYS:
        if isinstance(raw.get(key), str):
            cfg[key] = raw[key]
    return cfg


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return defaults()
    except OSError:
        return defaults()
    try:
        return clean(json.loads(text))
    except ValueError:
        try:
            shutil.copyfile(path, path.with_name(path.name + ".bad"))
        except OSError:
            pass
        return defaults()


def save(cfg: dict, path: Path | None = None) -> None:
    """Write the whole file atomically (temp file, then replace)."""
    path = path or config_path()
    data = json.dumps(clean(cfg), indent=2)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(data + "\n", encoding="utf-8")
    os.replace(tmp, path)


def mode_register_int(cfg: dict) -> int:
    return int(cfg["mode_register"], 2)
