# keyer-mac — Master Plan

A macOS PyQt6 app that talks to a K1EL WinKeyer over serial, sends typed
and canned CW messages, and exposes a local XMLRPC bridge for logging
software macros — a macOS port of mbridak's PyWinKeyerSerial.

Readable paths for this build: `pywinkeyerserial/` (reference
implementation, https://github.com/mbridak/PyWinKeyerSerial) and
`keyer-win-ui.png` (UI reference screenshot).

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
2. Interface: single main window — device dropdown (top), sent-text output
   box, free-text input box, speed spinbox, 6 canned-message
   buttons+fields, settings gear opening a keyer-mode dialog (Iambic A/B,
   Ultimatic, Bug, paddle swap, echo-back, autospace, CT spacing).
3. Data: local serial connection to a K1EL WinKeyer (USB/serial, macOS
   device path e.g. /dev/cu.usbserial-*, not /dev/ttyUSB0); local-only
   XMLRPC server on 127.0.0.1:8000 exposing k1elsendstring, setspeed,
   sendblended, tuneon, tuneoff, clearbuffer — no auth, no rate limit.
4. Persistence: flat dotfile ~/.keyer-mac.json in $HOME, written whole-file
   on any message-field edit — same approach as mbridak's
   ~/.pywinkeyer.json, no macOS-convention config dir.
5. Out of scope: xdg icon/.desktop installation, Linux menu registration
   (no macOS equivalent implemented in v1 — dock icon/app bundling
   deferred).

## Tech

1. Concurrency: single Qt event loop (QApplication.exec) + two QTimers —
   100ms serial-poll (echo/status/pot-speed bytes) and 250ms XMLRPC-bridge
   poll — plus one QThread running the blocking XMLRPC server
   (serve_forever). Same model ports unchanged to macOS; no Mac-specific
   concurrency issue in the source.
2. Layout:
   keyer_mac/
   ├── __init__.py
   ├── __main__.py        # bootstrap + main window (ported from source)
   ├── settings.py        # settings dialog (direct port)
   ├── main.ui / settings.ui
   └── resources/         # icons — .icns added for mac, source .png/.svg dropped
   tests/
   tools/
   requirements.txt · requirements-lock.txt · pyproject.toml
3. Serial I/O stays non-blocking on the UI thread (timeout=0), matching
   source — no dispatch-off-UI-thread work needed beyond the existing
   XMLRPC thread.
4. Known limitations (inherited from source, kept for parity unless told
   otherwise): global-variable + timer-poll bridge from XMLRPC thread to
   UI thread instead of Qt signals/slots; bare `except` in the serial-poll
   loop triggers a full reconnect on any read error; POTSET hardcodes a
   5–55 WPM pot range.
5. Delivery: py2app (setuptools command) building a macOS .app bundle.
   Config: ~/.keyer-mac.json (Spec §4). Log: stderr only, matching
   source's logging.basicConfig — no log file.
6. Stack override (replaces seed's Windows/tkinter default): PyQt6 +
   pySerial, matching source — not tkinter. Retina/HiDPI scaling is
   handled automatically by Qt6 on macOS, no Per-Monitor-v2-style manual
   scaling code needed (unlike the Windows Tk case the seed warns about).

## Tasks

0. Environment — mostly already satisfied: git identity, `gh` auth, repo
   jcarter-labs/keyer-mac (private) created and verified, Python 3.13.15
   venv in place (`keyer-mac/.venv`). Remaining: install PyQt6 + pySerial
   into .venv, verify import versions with real output.
1. Constitution check — walk Spec/Tech against the 11 rules; log kept
   deviations (e.g. global-variable XMLRPC bridge, bare-except reconnect,
   hardcoded pot range — Tech §4) as rule / why / rejected alternative.
2. External interfaces → Spec §3 — DEFERRED until the K1EL WinKeyer is
   physically connected (operator locating/connecting hardware). Live
   diagnostic against the real device, no mocks, per Verification
   Standard: open real macOS serial device, send host-open command
   (0x00 0x02), read version response; verify XMLRPC server on
   127.0.0.1:8000 answers a real k1elsendstring call.
3. Core logic → Spec §2–3 — port WinKeyer class (send, sendblended,
   tuneon/off, clearbuffer, setspeed, potspeed, mode-register bit
   packing), settings dialog, ~/.keyer-mac.json dotfile persistence
   (Spec §4).
4. First runnable UI → Spec §2 — port main.ui/settings.ui, wire buttons,
   add the verified run command to README.
5. Tests — logic-only unit tests (mode-register bits, dotfile
   round-trip) run mocked/headless (QT_QPA_PLATFORM=offscreen); serial
   and XMLRPC behavior stay covered only by Task 2's live diagnostic, per
   Verification Standard — source has zero existing tests, so this is
   new coverage, not a port.
6. Polish pass, measured against keyer-win-ui.png → Spec §2 — per UI
   Fidelity rule, list each widget's anchor/justify and compare against
   the reference before declaring done.
7. End-of-build addendum — review corrections + deviation log, propose a
   Constitution diff.
