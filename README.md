# keyer-mac

A macOS PyQt6 app that talks to a K1EL WinKeyer over serial, sends typed
and canned CW messages, and exposes a local XMLRPC bridge for logging
software macros.

This is a macOS port of Michael Bridak's (K6GTE) **PyWinKeyerSerial**:
https://github.com/mbridak/PyWinKeyerSerial. Core logic (WinKeyer
protocol, mode-register bit packing, XMLRPC bridge) is ported directly
from that project to preserve proven protocol behavior; see
`masterplan-old.md` for the full plan and `deviation-log.md` for every
place this port deviates from the source.

## Running

```
source .venv/bin/activate
python3 -m keyer_mac
```

Plug the WinKeyer Mini in first or after: the Message box shows a
"Scanning for keyer… 8" countdown, then "Keyer found: WinKeyer v3.1 on
/dev/cu.usbserial-…, 20 WPM". If it cannot connect it says why, with a time
stamp, and tries again every 8 s; plugging the keyer in connects within about
2 s. Config persists to `~/.keyer-mac.json` (set `KEYER_MAC_CONFIG_PATH` to
redirect it, e.g. for tests).

![keyer-mac 1.1](keyer-mac-1.1.png)

v1.1 is checked on a real WK-mini (firmware 3.1), 2026-10-02: handshake, free
text, five canned messages, speed 6–34 WPM, the settings dialog, all six
XMLRPC methods, and three manual unplug/replug cycles. Numeric layout targets
are in `tools/ui_targets.json`; `python3 tools/ui_fidelity_check.py` measures
the real window against them.

## License

GPL-3.0-or-later, inherited from the source project. See `LICENSE`.

## Status

v1.1 built per `masterplan.md` (from `idea.md`). The v1.0 plan is kept as
`masterplan-old.md`. Known limitations are listed in `masterplan.md`.
