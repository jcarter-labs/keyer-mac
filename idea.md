# keyer-mac v1.1: app brief

Version 1.1 brief, drafted 2026-10-02 from `masterplan-old.md` (Spec), mbridak's PyWinKeyerSerial
README, `keyer-win-ui.png`, `keyer-mac-running.png`, and the changes below.
Answers the five questions of `masterplan-generator.md`.

## 1. What it does, for whom, like what

keyer-mac is a macOS PyQt6 app that drives a **K1EL WinKeyer Mini (WK-mini)**
over USB serial. It sends typed and canned CW messages, and exposes an XMLRPC
bridge so logging software can fire CW macros. Built for amateur-radio
operators running a WK-mini into a rig's key jack (e.g. a KX3).

Like: **PyWinKeyerSerial** by Michael Bridak, K6GTE
(https://github.com/mbridak/PyWinKeyerSerial, GPL-3.0). Behaviours that matter:
WinKeyer host protocol, mode-register bit packing, XMLRPC server on port 8000,
auto-saving messages to a dotfile. keyer-mac is GPL-3.0-or-later.

**The WK-mini has no speed pot or other controls.** The code always assumes a
WK-mini: the on-screen speed control is the only way to set speed, and
pot input is ignored.

## 2. Platforms

- Build and run: macOS on Apple Silicon, Python 3.13+, PyQt6, pySerial.
- Serial device: macOS path `/dev/cu.usbserial-*` (the WK-mini enumerates as
  USB 1a86:7523, a WCH CH340). The numeric suffix changes with the USB port,
  so never rely on a saved name alone.
- Delivery: `python3 -m keyer_mac` for now; py2app `.app` bundle later.

## 3. Features, most important first

1. **Reliable start-up** (§5): finds the WK-mini, initializes it from the
   JSON file, and says plainly when it is missing.
2. Send free text typed in the free-text box.
3. Five canned messages, each sent by its button, edited in place.
4. Speed control, 20 WPM default.
5. Settings dialog (gear): Iambic A/B, Ultimatic, Bug, paddle swap,
   echo-back, autospace, CT spacing.
6. XMLRPC bridge on `0.0.0.0:8000` (source parity; LAN exposure accepted
   2026-09-08), no auth: `k1elsendstring`, `setspeed`, `sendblended`,
   `tuneon`, `tuneoff`, `clearbuffer`. Example client:
   `xmlrpc.client.ServerProxy("http://localhost:8000").k1elsendstring("Hello World")`.
   A port-8000 conflict must not abort the app.
7. Info button: modal that opens with a summary: **"keyer-mac is an auto keyer
   written for the Mac to interface with a WinKeyer Mini via USB."** Below it:
   the app name and version, connected port,
   WinKeyer firmware version, config-file path, XMLRPC address and methods,
   the mbridak attribution and GPL notice, the statement **"Designed to work
   with the K1EL WinKeyer Mini"**, and the repo name
   **jcarter-labs/keyer-mac** (https://github.com/jcarter-labs/keyer-mac).

## 4. What the user enters or sets

| Item | Range / default |
|---|---|
| Port | dropdown of detected serial ports; editable |
| Speed | dropdown, even values 6–34 WPM, default **20** |
| Free text | up to 3 visible lines, scrolls |
| Message 1–5 | text, auto-saved on every edit |
| Settings dialog | mode register bits as in the seed Spec |

Persistence: `~/.keyer-mac.json`, written whole-file on any change.
Keys: `device`, `speed`, `1`–`5`, `mode_register`. A legacy key `6` is ignored
without error. `KEYER_MAC_CONFIG_PATH` redirects the file for tests.

## 5. Screen and data sources

**Screenshots.** Two references, with fixed roles. Target: the finished 1.1
window approaches `keyer-mac-running.png` plus the changes in this brief.
Precedence when they disagree: (1) this brief's stated changes; (2)
`keyer-mac-running.png`, for widget style, gear glyph, button shape, Mac
window chrome and spacing; (3) `keyer-win-ui.png`, for row order, the gray
window with white fields, and the element set. `keyer-win-ui.png`'s "send msg
N" text and "K6GTE PyWinKeyer" title are stale and ignored. Neither image
shows Info, the footer or the 5-row list, so those follow the table below.

Window title "keyer-mac". **Font: Arial everywhere** (labels, fields, buttons, dropdowns,
Info dialog). **Background: light gray `#ededed`, entry and display fields
white `#ffffff`** so they stand out (both measured from `keyer-win-ui.png`).

Top to bottom:

| Row | Content | Alignment |
|---|---|---|
| 0 | Label **"Message"**; **Info** button; gear ⚙ button (Info left of gear); port dropdown | label, Info, gear left in that order; dropdown right-aligned, **half the current width (~190 pt, was ~380 pt)** |
| 1 | Message box (the sent-text display): **3 lines**, full width, read-only | left-justified text |
| 2 | Label "Free text input" (left); label "Speed:" and speed dropdown (right) | label left; "Speed:" right-justified beside its dropdown |
| 3 | Free-text input box: **3 lines**, full width | left-justified |
| 4–8 | **5** rows: message field (left, most of the width) + "msg N" button (flush right, 65 px) | uniform row spacing |
| 9 | Footer: **build date** (`YYYY-MM-DD`, constant `__build_date__` beside `__version__`, not read from the clock) bottom-left; **"v1.1"** bottom-right | left / right |

The window shrinks to fit the shorter boxes and one fewer message row.
The version string lives in one constant, `__version__ = "1.1"`.

Data sources: the WK-mini over serial (version byte, echo-back, status), and
`~/.keyer-mac.json`.

### Initialization (the main change in 1.1)

Start-up must work first time, every time. Today's failures: the port list is
built once, so a device plugged in after launch never appears; a virtual port
(`cu.debug-console`) gets saved and restored over the real one; the USB suffix
moves between ports.

1. **Discover**: list ports at launch, on opening the dropdown, and every 2 s
   while no WinKeyer is connected, so hot-plug works without a restart.
2. **Choose**: try the saved port if it exists; otherwise probe each real USB
   serial candidate (pyserial `vid` not None). Never auto-select, and never
   save, a virtual port (`debug-console`, `Bluetooth-Incoming-Port`, paired
   Bluetooth audio).
3. **Handshake**: Host Open and read the version byte, with the existing
   0.3 s close/reopen pad and 3 retries.
4. **Status in the message box** (replaces the line each second):
   - while scanning: **"Scanning for keyer… 8"** counting down to 0 (8 s,
     matching the worst-case handshake time);
   - on success: **"Keyer found: WinKeyer vX.Y on <port>"**;
   - at 0 with nothing found: **"Keyer missing: no WinKeyer detected. Plug it
     in; it will connect automatically."** Keep rescanning (§5.1), trying again
     every 8 s with the same countdown starting over at 8 (no growing delays);
     a later find replaces the message with "Keyer found…". Any new scan,
     including a dropdown re-pick, restarts the countdown at 8.
5. **Initialize from JSON on every successful connect**, in this order: mode
   register, then speed (default 20 WPM if absent). Send every setting each
   time; never rely on what the device remembers from earlier sessions.
6. **Verify**: speed and mode are sent only after the handshake has verified
   a WinKeyer. If a live diagnostic proves the speed can be read back, compare
   it with the value sent; if not, the check is that the writes returned
   without error and the keyer still answers an echo test afterwards. The
   message box then shows "Keyer found: WinKeyer vX.Y on <port>, 20 WPM".

**Diagnostics:** every connect or send failure prints a time-stamped line with
its reason in the Message box, so problems are diagnosed in use.

**Acceptance:** a re-runnable script does 5 cold starts against the real
WK-mini, plus 3 manual unplug/replug cycles by the operator, with 0 failures.
The diagnostics, not a large repeat count, are the safeguard.

## Open items

1. **Speed readback.** A pot-less WK-mini may have no command to read back the
   current speed. Run a live diagnostic before building; if none exists, use
   the §5.6 fallback. Status: not yet proven.
2. **Date.** Decided: the build date, as a constant.
3. **Layout fidelity.** Window size, row heights and the ~190 pt dropdown width
   get a numeric check in `tools/ui_fidelity_check.py`, per the Standing Bar.

## Out of scope

Dock icon and `.icns` bundling, Linux desktop integration, auth or rate limits
on XMLRPC, pot-equipped WinKeyer support.
