# keyer-mac — Master Plan

A macOS PyQt6 app that talks to a K1EL WinKeyer over serial, sends typed
and canned CW messages, and exposes a local XMLRPC bridge for logging
software macros — a macOS port of mbridak's PyWinKeyerSerial.

Readable paths for this build: `pywinkeyerserial/` (reference
implementation, https://github.com/mbridak/PyWinKeyerSerial) and
`keyer-win-ui.png` (UI reference screenshot).

**Version note:** this plan records the v1.0 build (Tasks 0–6, done). The
v1.1 changes (WK-mini only, 5 messages, Info button, Arial, new start-up
sequence) are specified in `idea.md`; where the two differ, `idea.md` governs
v1.1 and the sections below are history until the v1.1 masterplan replaces them.

## Constitution

1. **Build only from this document** and named reference artifacts. Name the
   readable paths at build start; anything unnamed is off-limits.
   *Prevents: a clean-room build copying a finished one.*
2. **Re-read this Constitution before each numbered task.**
   *Prevents: early rules decaying deep in a long build.*
3. **Preflight before live action.** No external-service call until preflight
   completes, even if credentials arrive with the request. An unexpected
   failure stops for the operator; a pre-declared fallback is tried unasked
   and reports only once exhausted.
   *Prevents: hammering someone's service on unverified details.*
4. **Verify → Build → Test → Commit.** Prove any network/protocol/hardware
   command with a live diagnostic before writing code around it; the
   diagnostic uses the app's real identity, never a stand-in.
   *Prevents: untested assumptions, and phantom bugs caused by the
   diagnostic.*
5. **Ask only after exhausting reachable evidence**, and say what you
   checked. Executing a decision the operator already made is not a new
   question.
   *Prevents: asking what is discoverable.*
6. **Done is a pasted artifact** — a fresh run's pass/fail output, never a
   description or a resemblance.
   *Prevents: defects shipping as done on eyeballing.*
7. **Documented commands run as given, per shell, not per platform.** You
   ran it from a clean shell and showed the output. Fix a failing one in the
   same turn, reusing the exact verified string.
   *Prevents: handing over a broken command twice.*
8. **Two failed attempts — stop.** Name and take the measurement that
   separates the competing explanations. The stop lifts on evidence, never
   on a new idea.
   *Prevents: a third guess dressed up as a fix.*
9. **One concern per commit**, and mark unverified behavior unverified in
   code and commit messages.
   *Prevents: unreviewable commits; aspiration recorded as fact.*
10. **Tests touch only the project and runner temp dirs.** Redirect
    $HOME/env-derived paths suite-wide and assert it.
    *Prevents: corrupting the operator's real data.*
11. **`git rev-parse --show-toplevel` must match this project** before any
    init/remote/commit.
    *Prevents: committing into the parent repo.*

## Spec

1. Targets: macOS (Apple Silicon) · Python 3.13+ · PyQt6 · pySerial (pinned
   versions TBD in requirements-lock).
2. Interface: single main window titled "keyer-mac" (replaces source's
   .ui title property "K6GTE winkeyerserial", which had drifted from the
   "K6GTE PyWinKeyer" shown in keyer-win-ui.png anyway) — device dropdown
   (top), sent-text output box, free-text input box, speed spinbox, 6
   canned-message buttons+fields [v1.1: 5 messages, speed dropdown 5–35,
   Info button, Arial; see idea.md], settings gear opening a keyer-mode
   dialog (Iambic A/B, Ultimatic, Bug, paddle swap, echo-back, autospace,
   CT spacing).
3. Data: local serial connection to a K1EL WinKeyer (USB/serial, macOS
   device path e.g. /dev/cu.usbserial-*, not /dev/ttyUSB0); XMLRPC server
   bound to 0.0.0.0:8000 (source parity, chosen over localhost-only —
   operator accepted the LAN-exposure tradeoff on 2026-09-08 rather than
   deviate from source's binding) exposing k1elsendstring, setspeed,
   sendblended, tuneon, tuneoff, clearbuffer — no auth, no rate limit.
4. Persistence: flat dotfile ~/.keyer-mac.json in $HOME, written whole-file
   on any message-field edit — same approach as mbridak's
   ~/.pywinkeyer.json, no macOS-convention config dir.
5. Out of scope: xdg icon/.desktop installation, Linux menu registration
   (no macOS equivalent implemented in v1 — dock icon/app bundling
   deferred).

## Tech

1. Concurrency: single Qt event loop (QApplication.exec) + two QTimers —
   100ms serial-poll (echo/status bytes; pot bytes are discarded since
   deviation-log #10) and 250ms XMLRPC-bridge
   poll — plus one QThread running the blocking XMLRPC server
   (serve_forever). Same model ports unchanged to macOS; no Mac-specific
   concurrency issue in the source.
2. Layout:
   keyer_mac/
   ├── __init__.py
   ├── __main__.py        # bootstrap + main window (ported from source)
   ├── settings.py        # settings dialog (direct port)
   ├── main.ui / settings.ui
   └── resources/         # icons — .icns added for mac, source .png/.svg
                           # and JetBrainsMono-Regular.ttf dropped (system
                           # font fallback for the settings-gear glyph)
   tests/
   tools/
   requirements.txt · requirements-lock.txt · pyproject.toml
3. Serial I/O stays non-blocking on the UI thread (timeout=0), matching
   source — no dispatch-off-UI-thread work needed beyond the existing
   XMLRPC thread.
4. Known limitations (inherited from source, kept for parity unless told
   otherwise): global-variable + timer-poll bridge from XMLRPC thread to
   UI thread instead of Qt signals/slots; bare `except` in the serial-poll
   loop triggers a full reconnect on any read error [narrowed to
   SerialException with backoff, deviation-log #8]; POTSET hardcodes a
   5–55 WPM pot range [pot input is ignored on the WK-mini, #10].
5. Delivery: py2app (setuptools command) building a macOS .app bundle.
   Config: ~/.keyer-mac.json (Spec §4). Log: stderr only, matching
   source's logging.basicConfig — no log file.
6. Stack override (replaces seed's Windows/tkinter default): PyQt6 +
   pySerial, matching source — not tkinter. Retina/HiDPI scaling is
   handled automatically by Qt6 on macOS, no Per-Monitor-v2-style manual
   scaling code needed (unlike the Windows Tk case the seed warns about).
7. Settings dialog import: clean absolute `from keyer_mac.settings import
   Settings` — source's script/package dual try/except import isn't
   needed since keyer_mac has no loose-script entry point.

## Tasks

0. Environment — mostly already satisfied: git identity, `gh` auth, repo
   jcarter-labs/keyer-mac (private) created and verified, Python 3.13.15
   venv in place (`keyer-mac/.venv`). Remaining: install PyQt6 + pySerial
   into .venv, verify import versions with real output.
1. Constitution check — walk Spec/Tech against the 11 rules; log kept
   deviations (e.g. global-variable XMLRPC bridge, bare-except reconnect,
   hardcoded pot range — Tech §4) as rule / why / rejected alternative.
2. External interfaces → Spec §3 — DONE. Live diagnostics against the
   real K1EL WinKeyer at /dev/cu.usbserial-8340 (`tools/
   winkeyer_diagnostic.py`, `tools/winkeyer_xmlrpc_diagnostic.py`), no
   mocks, per Verification Standard: host_open returned version 0x1f
   (firmware v3.1); POTSET + pot-speed query decoded to 55 WPM; XMLRPC
   server on 0.0.0.0:8000 answered a real k1elsendstring("TEST") call
   with the device not wired to a radio (operator-confirmed before
   sending).
3. Core logic → Spec §2–3 — DONE. Ported WinKeyer class (send,
   sendblended, tuneon/off, clearbuffer, setspeed, potspeed, mode-
   register bit packing), settings dialog, and ~/.keyer-mac.json
   dotfile persistence (Spec §4) with the KEYER_MAC_CONFIG_PATH seam.
   main.ui/settings.ui also ported here (needed to load the class at
   all) — button wiring (Task 4's stated scope) came along with the
   direct port, since it's the same __init__ that connects signals.
   Verified: headless smoke test against real hardware, clean shutdown,
   exit 0 — see the `feat: port WinKeyer class` commit.
4. First runnable UI → Spec §2 — DONE. `.ui` port and button wiring
   landed in Task 3 (same __init__ that ported everything else); the
   remaining piece — the verified run command in README — added now.
   Confirmed by a real (non-headless) run against the physical WinKeyer:
   window opens titled "keyer-mac", device auto-detected, speed spinbox
   synced live to the pot position, all 6 message fields/buttons and
   the settings gear present.
5. Tests — DONE. 5 passing pytest tests (`tests/`), headless
   (QT_QPA_PLATFORM=offscreen): mode-register bit packing/unpacking
   (`Settings`, 3 tests) and dotfile round-trip (`WinKeyer.loadsaved`/
   `savestuff`, 2 tests). Required deferring `keyer_mac.__main__`'s
   bootstrap into `main()` (source ran it at module level) and fixing a
   latent mutable-class-attribute bug the tests caught directly — see
   deviation-log.md #4. Serial/XMLRPC behavior stays covered only by
   Task 2's live diagnostics, per Verification Standard.
6. Polish pass, measured against keyer-win-ui.png → Spec §2 — DONE.
   `tools/ui_fidelity_check.py` (new, re-runnable per the Standing Bar on
   numeric layout claims) launches WinKeyer headless, reads real widget
   geometry post-layout, and grabs an actual rendered screenshot. Window
   size 579×594 matches main.ui's declared geometry exactly.

   Per-widget anchor/justify vs. the reference, all matching:
   - "Sent Text" label: top-left, AlignLeft|AlignVCenter.
   - Settings gear (⚙): top row, between label and device dropdown —
     renders clearly here (system font fallback, per the pinned Task-3
     decision); barely visible in the reference's Linux/GTK rendering,
     not a layout difference.
   - Device dropdown: top-right, spans remaining row width.
   - Sent-text output box: full width, left-justified text, below row 0.
   - "Free text input" label: left, AlignLeft|AlignVCenter.
   - "Speed:" label: AlignTrailing|AlignVCenter, immediately left of the
     spinbox — matches reference's right-justified placement.
   - Speed spinbox: same row, right side.
   - Free-text input box: full width, below that row.
   - Six msg rows: QLineEdit (left-justified, most of row width) + fixed
     70px QPushButton flush right — uniform 34px row spacing measured
     across all six (msg1 y=378 through msg6 y=548).

   One real discrepancy found and resolved: the reference screenshot is
   byte-identical to pywinkeyerserial's own bundled `pic/WINKEYERSCREEN.png`
   — the source repo's stale README image. Its "send msg N" button text
   and "K6GTE PyWinKeyer" title predate the current main.ui (which has
   said "msg N" and "K6GTE winkeyerserial" across its whole git history —
   confirmed via `git log -p`). Current source is authoritative over its
   own stale screenshot; keyer_mac's "msg N" labels (already ported
   as-is from current source) needed no change. Window title stays
   "keyer-mac" per the earlier pinned decision, unaffected either way.
7. End-of-build addendum — review corrections + deviation log, propose a
   Constitution diff.
