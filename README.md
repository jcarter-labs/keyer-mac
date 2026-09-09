# keyer-mac

A macOS PyQt6 app that talks to a K1EL WinKeyer over serial, sends typed
and canned CW messages, and exposes a local XMLRPC bridge for logging
software macros.

This is a macOS port of Michael Bridak's (K6GTE) **PyWinKeyerSerial**:
https://github.com/mbridak/PyWinKeyerSerial. Core logic (WinKeyer
protocol, mode-register bit packing, XMLRPC bridge) is ported directly
from that project to preserve proven protocol behavior; see
`masterplan-seed.md` for the full plan and `deviation-log.md` for every
place this port deviates from the source.

## License

GPL-3.0-or-later, inherited from the source project. See `LICENSE`.

## Status

In development — see `masterplan-seed.md` Tasks for current progress.
