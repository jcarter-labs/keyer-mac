# Constitution

1. Build from masterplan.md, idea.md and my screenshots; borrow language, tools, specs, or open-source code from examples as I choose.
2. At the start of the build, check tools, libraries, GitHub login, that this folder is its own repo root, and that each data source's host and port can be reached, on my platforms; show pass/fail.
3. After each change, measure the app against the Spec's screen list; show pass/fail.
4. After each working step: run all tests, show me proof, commit, and push to GitHub. Keep going within a stage; stop only at stage end, on a failed test, after two failed fixes, or for my decision.
5. When code and masterplan disagree, propose only major changes, one line each; update the masterplan after I approve.
6. One concern per commit.
7. Mark unverified behavior unverified, in code and in commit messages.
8. Tests touch only the project and runner temp dirs; redirect `$HOME` and env-derived paths suite-wide, and assert it.
9. Prove any hardware command with a live diagnostic before writing code around it; the diagnostic uses the app's real identity, never a stand-in.

# Spec

keyer-mac v1.1 is a macOS auto keyer for the K1EL WinKeyer Mini over USB. The operator types free text or presses one of five canned-message buttons, and the keyer sends CW to the rig's key jack. A speed dropdown (even values 6–34 WPM, default 20) and a settings dialog control sending. The Message box shows sent text and connection status. A local XMLRPC server on port 8000 lets logging software fire CW macros. It is a Mac rewrite of mbridak's PyWinKeyerSerial (GPL-3.0), laid out like `keyer-mac-running.png`. Messages, speed and settings persist in `~/.keyer-mac.json`, and every setting is re-sent to the keyer on every connect.

## Screen list

Window "keyer-mac", about 579 pt wide, 15 pt margins, 10 pt between columns, Arial throughout. Background gray `#ededed`; the two text boxes and five message fields white `#ffffff`. Precedence when the two screenshots differ: this plan's stated changes, then `keyer-mac-running.png` (widget style, spacing, window chrome), then `keyer-win-ui.png` (row order, element set, gray window with white fields; its "send msg N" text and "K6GTE PyWinKeyer" title are stale and ignored). Heights come from the layout; every numeric target, including width, is the measured value in `tools/ui_targets.json`, and the 579 pt here is only the starting value.

| # | Element | Type | Where it sits |
|---|---|---|---|
| 1 | "Message" | label | Row 0, far left, vertically centered |
| 2 | "Info" | button | Row 0, right of the label, left of the gear |
| 3 | ⚙ | button (opens settings dialog) | Row 0, right of Info, left of the port dropdown |
| 4 | Port dropdown | editable combo box | Row 0, right-aligned to the margin, about 190 pt wide (half the 1.0 width) |
| 5 | Message box | read-only text, 3 lines, white | Row 1, full width, left-justified; sent text and status |
| 6 | "Free text input" | label | Row 2, far left |
| 7 | "Speed:" | label | Row 2, right-justified, directly left of the speed dropdown |
| 8 | Speed dropdown | combo box, even values 6–34 WPM (15 entries), default 20 | Row 2, flush right |
| 9 | Free-text input | text edit, 3 lines, white | Row 3, full width, left-justified |
| 10 | Message fields 1–5 | single-line text, white | Rows 4–8, left, all but the button column |
| 11 | "msg 1" to "msg 5" | buttons, 65 pt wide (measured) | Rows 4–8, flush right, one per field |
| 12 | Build date | label, `YYYY-MM-DD` | Row 9, bottom-left |
| 13 | "v1.1" | label | Row 9, bottom-right |

Rows 4–8 are evenly spaced.

**Message box content:** the countdown updates one line in place; other status messages append as new lines; keyer echo appends as it arrives; the box clears on each new connect. Echo appears only when echo-back is on in settings; tests assume the default register has it on (verified in step 2.3).

| Type size (line spacing about 1.3×; no added borders or bold) | Size |
|---|---|
| Message box, free-text input, message fields 1–5 | 16 pt |
| Port dropdown, speed dropdown | 14 pt |
| Labels, Info/⚙/"msg N" buttons | 13 pt |
| Footer (date, "v1.1") | 11 pt |

## Features

1. **Start-up and connect.** The user launches with the keyer plugged in, or plugs it in later.
   - The Message box shows "Scanning for keyer… 8", counting down once a second to 0. The countdown covers the whole first scan including handshake retries; a handshake still running at 0 is allowed to finish before "missing" shows.
   - Success: "Keyer found: WinKeyer vX.Y on <port>, N WPM" (N = the speed actually sent), and the port dropdown selects that port.
   - No keyer after 0 and any running handshake: "Keyer missing: no WinKeyer detected. Plug it in; it will connect automatically." It keeps rescanning every 2 s; retries back off 1 s, doubling to 30 s.
   - A keyer plugged in later is found within 2 s of enumeration plus handshake time (8 s at most), no restart.
   - The saved port is tried first if it exists; otherwise only ports with USB ID `1a86:7523` are probed. Other ports are listed in the dropdown but never auto-probed, so unrelated serial devices are not disturbed. Virtual ports (`cu.debug-console`, `cu.Bluetooth-Incoming-Port`) are never auto-selected or saved.
   - A port the user picks or types (Enter) is tried at once and kept until relaunch or disconnect; auto-probing stops while it is set.
   - `device` is saved only after a successful handshake.
   - Mode register, then speed, are sent from `~/.keyer-mac.json` on every connect (speed 20 if absent). Handshake and checks: see Data sources.
   - Every failure is printed in the Message box with a time stamp and its reason (see Diagnostics), so a problem can be diagnosed in use.
   - Pass (a cold start is a fresh process launch with the keyer plugged in and the port previously closed, not a keyer power cycle): 5 cold starts and 3 manual unplug/replug cycles, 0 failures. Not a statistical gate: the Message box diagnostics are the main safeguard.
2. **Free-text sending.** Each typed character is sent as typed, upper-cased. Deleting a character erases it from the keyer's buffer if not yet sent. The Message box shows the characters the keyer echoes as it sends. The box shows 3 lines and scrolls.
3. **Canned messages.** Typing in any of 5 fields and pressing "msg N" (N = 1–5) sends that text, upper-cased. Each edit saves at once to `~/.keyer-mac.json` (keys `1`–`5`); relaunch restores all five. A leftover key `6` is ignored without error.
4. **Speed.** Even values 6, 8 … 34 WPM, default 20. Picking a value sends it at once and saves it as `speed`; the dropdown always shows the value last sent. The WK-mini has no pot, so no pot input changes it. XMLRPC `setspeed` updates the dropdown too.
5. **Settings (⚙).** The dialog sets Iambic A/B, Ultimatic, Bug, paddle swap, echo-back, autospace and CT spacing. Saving packs the mode register (default `11001110`), writes it to the keyer, and saves it as `mode_register`. Cancel changes nothing.
6. **XMLRPC bridge.** `http://<host>:8000`, bound to `0.0.0.0`, no authentication. Methods: `k1elsendstring(str)`, `setspeed(int)`, `sendblended(str)`, `tuneon()`, `tuneoff()`, `clearbuffer()`. `setspeed` accepts only even values 6–34; anything else returns an XMLRPC fault and changes nothing. Pass: a call from another process sends the string and returns within 1 s. If port 8000 is in use, the app still starts and says so in the Message box.
7. **Info.** The button opens a dialog that starts with "keyer-mac is an auto keyer written for the Mac to interface with a WinKeyer Mini via USB," then: version, connected port, WinKeyer firmware, config-file path, XMLRPC address and methods, the mbridak attribution and GPL notice, "Designed to work with the K1EL WinKeyer Mini," and `jcarter-labs/keyer-mac` with its URL. Closing changes nothing.
8. **Diagnostics.** When a connect or a send fails, the Message box adds a line `HH:MM:SS <what failed>: <reason>`: no WinKeyer-mini visible; port could not be opened (with the system error); opened but no answer to host open (3 tries); answered but failed the echo test; disconnected, with the cause (serial error, no answer to the idle echo test, or which command's write failed). Each retry adds `HH:MM:SS Retrying in N s`. A successful connect prints none of these.
9. **Footer.** The date is the build date (`YYYY-MM-DD`), a constant `__build_date__` beside `__version__`, not read from the clock. "v1.1" is the version.

## Data sources

| # | Source | Provides | Check |
|---|---|---|---|
| 1 | **WinKeyer Mini, USB serial** (WCH CH340, `1a86:7523`, `/dev/cu.usbserial-*`; 1200 baud, 8N2, DTR on) | Version byte, echo, status bytes; accepts commands | Steps below |
| 2 | `~/.keyer-mac.json` | `device`, `speed`, `1`–`5`, `mode_register` | Missing file gives defaults; unreadable JSON gives defaults and the bad file is kept as `~/.keyer-mac.json.bad` (unit test) |
| 3 | pyserial `comports` | Candidate ports; USB vendor id marks real hardware | Unit tests on fake lists: virtual-only, real-only, mixed, suffix changed, none |
| 4 | XMLRPC clients (inbound, port 8000) | Strings, speed, tune and clear commands | Bind succeeds or the Message box says so; a real client call reaches the keyer within 1 s |
| 5 | `__build_date__`, `__version__` | Footer | Unit test: footer text equals the two constants |

**WinKeyer checks, in order (first connect and every reconnect):**
1. **Open** at 1200/8N2, DTR on, after a 0.3 s close/reopen pad that is process-wide (shared by every worker). **Verified live (2026-10-02):** with ~0 s between a close and the next open about 25% of handshakes stalled for several seconds (no recovery by retry or reopen); at 0.3 s or more, 0 of 80. Failure means the "Keyer missing" flow; no commands sent.
2. **Host Open** (`00 02`). Pass: exactly one version byte (1.0 returned `0x1f`, firmware v3.1). Up to 3 tries, 0.3 s apart, on the already-open port; never reopen the port per try.
3. **Send every setting, every time**, never relying on what the keyer or an earlier session left behind, in this order:
   1. mode register from `mode_register` (default `11001110`);
   2. speed from `speed` (default 20 WPM);
   3. the pinned parameters the app does not expose, in `PINNED_PARAMETERS` in `winkeyer.py`: weighting 50 (`03`), dit/dah ratio 50 (`17`), first extension 0 (`10`), key compensation 0 (`11`), paddle switchpoint 50 (`12`), Farnsworth off (`0D 00`), PTT lead-in 0 and tail 0 (`04`). Sidetone (`01`) and pin configuration (`09`) are never written: wiring-specific, and a wrong pin value could disable keying. **Unverified:** the values are the K1EL defaults as remembered; the WK-mini cannot report them back, so they are checked only by 20/20 live connects where the writes were accepted and the echo test still answered.
4. **Verify.** An echo test (admin `04` + a test byte; verified live, 20/20) must return that byte after the settings are sent. **Verified (2026-10-02):** the WK-mini cannot report its speed back (admin `07` is silent; the pot query ignores the set speed). The check is therefore "writes succeeded and echo test passed."
5. **Report.** Only now does the Message box show "Keyer found: WinKeyer vX.Y on <port>, N WPM."

**While connected:** an idle echo test every 10 s (interval proposed; upstream added a keepalive in 2026), so a silent hang is caught without a send.

**After a reconnect:**
- Triggers: a serial read or write error, the port missing from enumeration, or an echo test with no answer.
- The Message box shows "Keyer disconnected. Scanning for keyer… 8" and the countdown restarts. Steps 1–5 run again in full, with settings re-sent from the JSON, not cached.
- The XMLRPC server stays up. A call that arrives while disconnected is dropped, not queued, and the Message box says so. **Proposed.**
- Settings changed in the UI while connected (speed, mode register) are sent at once and saved.
- Checked by 3 manual unplug/replug cycles, each ending with a passing echo test and "Keyer found" (the speed is re-sent from the JSON). 0 failures, and every failure along the way is printed with its reason.

## Scope for 1.1

**In:** everything above. **Decided:** unexposed WinKeyer parameters are pinned to factory defaults on every connect; XMLRPC calls while disconnected are dropped with a Message box note; the footer date is the build date. **Waits:** `.app` bundle and icon (py2app), Linux desktop integration, XMLRPC authentication or rate limits, support for WinKeyers with a speed pot.

# Tech

## Stack (chosen)

- **Python 3.13** in `./.venv`, deps pinned in `requirements-lock.txt`.
- **PyQt6**: what upstream and 1.0 use; GPL-3.0 licence is no obstacle; Qt scales for Retina.
- **pySerial** for serial; stdlib **`xmlrpc.server`** for the bridge. No new runtime dependencies.
- **pytest** plus **pytest-qt** (new; headless via `QT_QPA_PLATFORM=offscreen`).
- No packaging in 1.1. Free to restructure from upstream; GPL-3.0-or-later `LICENSE` and the mbridak attribution stay.

## Install and check

macOS on Apple Silicon only. Run from a fresh shell with `.venv` active; show pass/fail at build start (rule 2).

| Needs | Check | Pass |
|---|---|---|
| Python 3.13 | `python3 --version`, `which python3` | 3.13.x, path inside `.venv` |
| PyQt6 6.11.0 (Qt 6.11.2, sip 13.12.0) | `python3 -c "import PyQt6.QtCore as c; print(c.PYQT_VERSION_STR)"` | `6.11.0` |
| pySerial 3.5 | `python3 -c "import serial; print(serial.__version__)"` | `3.5` |
| pytest, pytest-qt | `python3 -m pytest --version`, `pip show pytest-qt` | both present, pinned in `requirements-dev.txt` |
| Arial | `QFontDatabase.families()` contains "Arial" | present; else fall back to Helvetica and say so |
| git, gh | `git --version`, `git config user.name user.email`, `gh auth status` | identity set; logged in as `jcarter-labs` |
| Repo root | `git rev-parse --show-toplevel` | `/Users/N6YU/Projects/keyer-mac` |
| Remote | `git remote -v`, `git ls-remote origin` | HTTPS `jcarter-labs/keyer-mac`; answers |
| WinKeyer Mini on USB | `ls /dev/cu.usbserial-*`, `system_profiler SPUSBDataType` | one port; vendor `1a86`, product `7523`; no driver install |
| Port 8000 free | `lsof -i :8000` | nothing listening (or the app reports the conflict, never aborts) |

A failed row stops the build for your decision. Close the keyer-mac window before the WinKeyer row; an open app holds the port.

## Responsiveness

RULE (as given): Keep the app responsive while it works, never stuck waiting on data or input.

The UI thread never sleeps, reads serial, or waits on a handshake. One worker `QThread` owns the serial port and talks to the UI only through Qt signals. The countdown is a UI timer, so it ticks during a handshake. The XMLRPC server runs in its own thread and forwards calls as signals. Test: with a fake port that stalls 3 s, UI ticks keep arriving at 1 s intervals (pytest-qt).

## Modules

Under `keyer_mac/`, each testable alone; only `worker.py` and `ui.py` need Qt.

1. `config.py`: load/save `~/.keyer-mac.json`, defaults, bad-file handling; redirected `$HOME`.
2. `ports.py`: enumerate, classify real vs virtual by USB vendor id, order candidates; pure functions on fake lists.
3. `winkeyer.py`: protocol only: command bytes, mode-register packing, connect sequence, on an injected serial-like object (fake in tests, real in `tools/`).
4. `worker.py`: serial thread: scan, countdown source, connect, reconnect with backoff, send queue, signals; fake port.
5. `bridge.py`: XMLRPC thread; calls become signals; drops calls while disconnected; real `ServerProxy` against a stub worker.
6. `ui.py`: window, layout, Arial and sizes, Message box, footer, Info dialog; no serial code; pytest-qt plus the fidelity script.
7. `settings.py`, `__init__.py`, `__main__.py`: settings dialog; `__version__` and `__build_date__`; bootstrap only.

## Known limitations

RULE (as given): Keep a short list of known limitations in the masterplan; update it as we go.

1. WinKeyer Mini only; no speed pot; UI speed limited to even values 6–34 WPM.
2. XMLRPC binds `0.0.0.0:8000` with no authentication or rate limit (LAN exposure accepted 2026-09-08).
3. XMLRPC calls while disconnected are dropped, not queued.
4. Speed and the pinned parameters cannot be read back from the WK-mini (verified); they are checked by write success plus the echo test only. The pinned values themselves are unverified.
5. A missing keyer takes up to about 8 s to report.
6. The USB port-name suffix changes with the physical USB port, so a saved port name is only a first guess.
7. `__build_date__` is edited by hand at each release.
8. macOS Apple Silicon only; no `.app` bundle yet.
9. No stop-sending button in 1.1; `clearbuffer` is reachable only over XMLRPC.
10. The pad cannot span processes: relaunching the app within a fraction of a second of quitting it can still hit the stall; the worker's backoff recovers it.

# Tasks

RULE (as given): Test connections to outside data with real servers before building screens that depend on them.
RULE (as given): Get a simple version running early, then add features one at a time, testing each.

Rule 4 applies to every sub-step; "all tests" means the unit suite, and live checks run where a step says "live" and at each stage end. "Live" means the real WK-mini with the keyer-mac window closed. Paste pass/fail output; never describe it.

## Stage 1: Environment

| Step | Test | Works when |
|---|---|---|
| 1.1 Install and check | each Tech check | all 10 rows pass; pytest-qt installed and pinned |
| 1.2 Measure screenshots | extend `tools/ui_fidelity_check.py`: read geometry and colours from `keyer-mac-running.png` and `keyer-win-ui.png`, apply the brief's changes (half-width dropdown, 3-line boxes, 5 rows, type sizes), write `tools/ui_targets.json` | two runs print the same numbers; targets include window width, margins, dropdown width, row y-positions, button width, `#ededed`, `#ffffff` |
| 1.3 Test harness | pytest with `$HOME` redirected and asserted (rule 8) | an empty suite passes; a test touching the real `$HOME` fails |

**Done when:** every Install row shows PASS and `ui_targets.json` exists.

## Stage 2: Data connections (live), ending in a bare window

| Step | Test | Works when |
|---|---|---|
| 2.1 Port discovery | `ports.py` on the real machine | the WK-mini is the only candidate; `cu.debug-console` and Bluetooth ports rejected |
| 2.2 Handshake | `winkeyer.py` connect sequence, real device, app identity (rule 9) | one version byte (expect `0x1f`) and a passing echo test, 20 times in a row |
| 2.3 Settings diagnostic | live: read what the keyer allows; send factory-default parameters; test speed readback | results recorded in Known limitations ("unverified" becomes verified or "not possible"); pinned list and values written into the Spec |
| 2.4 XMLRPC | bind 8000; real `ServerProxy` calls `k1elsendstring("E")` | returns within 1 s; keyer echoes the character |
| 2.5 Bare window | window with only the Message box, running the countdown | 10 cold starts: each shows "Scanning for keyer… 8" ticking each second, then "Keyer found: WinKeyer vX.Y on <port>" |

**Done when:** 2.1–2.5 pass on the real keyer and diagnostic output is pasted.

## Stage 3: Core logic

| Step | Test | Works when |
|---|---|---|
| 3.1 `config.py` | unit, temp `$HOME` | defaults; round-trip of `device`, `speed`, `1`–`5`, `mode_register`; key `6` ignored; bad JSON becomes `.bad` plus defaults |
| 3.2 `ports.py` | unit, fake lists | virtual-only, real-only, mixed, suffix changed, none: right choice every time; a virtual port never saved |
| 3.3 `winkeyer.py` | fake serial | exact bytes for host open, mode register, speed, pinned parameters, echo test; 3 retries then failure |
| 3.4 `worker.py` | fake port, pytest-qt | scan, found, missing, disconnect, reconnect with backoff 1→30 s; settings re-sent in order on every connect; a stalled port does not stop 1 s UI ticks |
| 3.5 `bridge.py` | stub worker, real client | all six methods route; disconnected calls dropped with a note; port-8000 conflict does not abort |

**Done when:** all unit tests pass, plus 50 simulated disconnect/reconnect cycles on the fake port, 0 failures.

## Stage 4: Features, one at a time

Each is wired to the real worker, tested, and committed before the next.

| Step | Test | Works when |
|---|---|---|
| 4.1 Free text | live: type "TEST" | the keyer echoes T-E-S-T into the Message box; backspace erases an unsent character |
| 4.2 Five messages | live: fill and press msg 1–5 | each sends its own text; edits persist after relaunch; key `6` ignored |
| 4.3 Speed | live: choose 6, 20, 34 | each sent at once and saved; relaunch shows the saved value; 20 on a fresh file |
| 4.4 Settings | unit plus live | mode register matches the chosen bits; Cancel changes nothing |
| 4.5 XMLRPC | real client | six methods work on the live keyer |
| 4.6 Info | pytest-qt | summary line first; every listed item shows; closing changes nothing |
| 4.7 Footer | pytest-qt | text equals `__build_date__` and `__version__` |

**Done when:** every row passes in the same live session.

## Stage 5: UI polish and soak

| Step | Test | Works when |
|---|---|---|
| 5.1 Layout and type | `ui_fidelity_check.py` against `ui_targets.json` | every numeric target within 2 px; Arial; 16/14/13/11 pt; 3-line boxes; 5 rows; dropdown about 190 pt |
| 5.2 Start-up smoke | script: 5 cold starts, live keyer | 0 failures; each ends "Keyer found" with speed 20 |
| 5.3 Reconnect | 3 manual unplug/replug cycles by you | each ends "Keyer found" with no manual action; any failure shows its reason in the Message box |

**Done when:** 5.1–5.3 pass with output pasted, and a screenshot of the running app sits beside `keyer-mac-running.png`.

## Stage 6: Review

Review what went wrong and propose masterplan updates for my approval: every deviation from this plan, every unverified item left, and each rule that was hard to follow, one line each. Nothing changes in the masterplan until you approve.
