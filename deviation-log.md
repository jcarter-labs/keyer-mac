# Deviation Log

Logged per Constitution rule 1 (Task 1: Constitution check). Reviewed
7-Constitution walk-through against Spec/Tech; findings below.

## 1. Rule 10 vs Spec §4 (test isolation on the dotfile path)

**Rule:** Tests touch only the project and runner temp dirs; redirect
$HOME/env-derived paths suite-wide and assert it.
**Conflict:** Source hardcodes `os.path.expanduser("~")` for
`.pywinkeyer.json` with no override hook. Spec §4 keeps that dotfile
approach for parity. A literal port would force Task 5's dotfile
round-trip test to write into the operator's real `$HOME`.
**Decision:** Add one seam not present in source — a config-path resolver
(env var override, default unchanged at `~/.keyer-mac.json`) so tests can
redirect it. Production default behavior is unaffected.
**Rejected alternative:** Monkeypatch `os.path.expanduser` globally in
tests — fragile, patches stdlib rather than the app's own seam.

## 2. Rule 9 vs Tech §4 (known limitations kept for parity)

**Rule:** Mark unverified behavior unverified in code and commit messages.
**Conflict:** Tech §4 keeps three source quirks as-is rather than fixing
them: global-variable + timer-poll XMLRPC→UI bridge (not signals/slots),
bare `except` triggering full reconnect on any serial read error, and a
hardcoded 5–55 WPM pot range.
**Decision:** Kept for parity per Spec's port goal, not fixed silently —
each gets an explicit `# ported as-is, not hardened:` comment at point of
use and a callout in the commit that introduces it.
**Rejected alternative:** Rewrite the bridge with Qt signals/slots and
tighten the exception handling now — rejected to minimize behavioral
drift from the proven source in v1; revisit post-Task 6.

## 3. Rule 4 sequencing (Task 2 deferred)

**Rule:** Prove any hardware command with a live diagnostic before writing
code around it.
**Conflict:** Task 2 (live WinKeyer diagnostic) is deferred until hardware
is connected, but Task 3 (core logic) ports the same hardware-facing
methods (send, tuneon/off, setspeed, etc.).
**Decision:** Task 3 proceeds — code is written against the source's
already-documented protocol — but every hardware-facing method stays
marked unverified (rule 9) in code and commit messages until Task 2's live
diagnostic passes. Not a rejected alternative, just an accepted ordering
consequence of deferring Task 2 on operator instruction.

## 4. Rule 9/10 vs a latent source bug (mutable class-attribute default)

**Rule:** Every new piece of logic ships with at least one test (Standing
Bars); tests touch only project/runner temp dirs (rule 10).
**Conflict:** Source declares `settings_dict = {...}` as a `WinKeyer`
class attribute rather than setting it in `__init__`. Invisible in real
usage (`python3 -m keyer_mac` only ever creates one instance per
process), but Task 5's dotfile-round-trip test — which creates multiple
`WinKeyer()` instances in one process — caught it directly: a value
written by one instance leaked into a second instance's freshly-written
defaults, because both were mutating the same shared dict object.
**Decision:** Fixed, not ported as-is — moved the dict literal into
`__init__` so each instance gets its own. Zero behavior change for the
single-instance production path (the values and shape are identical);
this is a bug fix the test suite paid for itself, not a "kept for
parity" quirk like the three in §2.
**Rejected alternative:** Leave the class attribute as source has it and
work around the sharing in test fixtures (e.g. reset it between tests) —
rejected as preserving a real bug for tests to keep dodging, for no
production benefit.

## 5. Rule 9 vs a crash-on-recoverable-condition (RPCThread bind failure)

**Rule:** Mark unverified behavior unverified; more generally, a
recoverable condition shouldn't cost more than the feature it belongs to.
**Conflict:** Source's `RPCThread.run()` has no error handling around
`SimpleXMLRPCServer(("0.0.0.0", 8000), ...)`. Any bind failure (port
already in use — another instance, a leftover process, an unrelated
service) raises `OSError` inside a `QThread.run()` override; PyQt6's
default handling of an exception escaping such an override is to print
it and `abort()` the whole process. Confirmed live twice in one evening:
a leftover keyer_mac process from an earlier test run held port 8000,
and the next launch aborted the entire app — including the keyer itself
— over an XMLRPC-only problem.
**Decision:** Wrap the bind in `try/except OSError`, log the failure,
and return — the keyer and its UI keep working normally; only the
XMLRPC bridge is unavailable for that run. A behavioral change from
source, not just a testability seam, but justified: this crash mode has
nothing to do with the WinKeyer protocol Task 2/3 exists to preserve
faithfully, and losing the whole app over a mundane port conflict is a
worse failure than the three quirks kept for parity in §2.
**Rejected alternative:** Leave unguarded for source parity — rejected;
unlike the WinKeyer protocol quirks, an app-wide abort() over a
recoverable network condition serves no fidelity purpose and had
already produced two real crash reports before this fix.

## 6. Rule 9 vs a phantom pot line permanently overriding manual speed

**Rule:** Standing Bar — a control that can never actually be used isn't
a control. More generally, source's design (per its own docstring —
"the speed pot should work to change the code speed on the fly")
assumes a real potentiometer that only reports on an actual knob turn.
**Conflict:** Operator's WK-mini has no physical speed pot. Its ADC pot
input still floats/reads something, and the WinKeyer keeps reporting
that reading as an unsolicited pot-status byte on `getwaiting()`'s
100ms poll. Source's `potspeed()` unconditionally calls `setspeed()` on
every such byte, so the spinbox (and the device's actual speed) snapped
back to a stale phantom reading (35 WPM) every 100ms, making the
on-screen spinbox — the only speed control this hardware has — useless.
**Decision:** Track the last value each source (pot, spinbox) actually
reported, and only apply+broadcast a change when a source's new value
differs from its own last one. A stale, repeated pot echo is now
ignored; a genuine change on either line — a real knob turn on units
that have one, or a manual spinbox edit — still takes control exactly
as source intended. Symmetric by construction, so it costs nothing for
hardware with a working pot.
**Rejected alternative:** Ignore all pot-status bytes / only apply the
pot reading once at startup — rejected because it would silently break
live pot control on any WK unit that has a real, working potentiometer,
which is exactly the behavior source's docstring calls out as a
deliberate feature, not incidental.

Separately noted, not yet acted on: `main.ui`'s `spinBox_speed` widget
caps at 35 WPM (`minimum=5`, `maximum=35`), verbatim from source,
independent of POTSET's configured 5-55 WPM hardware range (§2). This
own-range mismatch predates today's fix and still limits the on-screen
control to 35 WPM max regardless of arbitration; raising it to match
POTSET's range is a candidate follow-up, pending operator decision.

## 7. Rule 9 vs an arbitrary auto-selected device silently persisting a virtual port

**Rule:** Standing Bar — a layout/behavior claimed to work needs a
re-runnable check, not an assumption; more generally, source's own
docstring goal ("talks to the WinKeyerUSB and WinKeyerSerial devices")
assumes the device it opens is actually a WinKeyer.

**Conflict:** Tonight's real incident: the operator's `~/.keyer-mac.json`
had `"device": "/dev/cu.Bluetooth-Incoming-Port"` saved — a macOS virtual
Bluetooth-serial-compatibility port with no WinKeyer, or anything, behind
it. Every launch opened it successfully at the OS level, then correctly
reported "is open but WinKeyer is not responding" — not a hardware
fault, purely the wrong device, consistently. Root cause traced to
`WinKeyer.__init__`'s `comports()` loop (ported verbatim from source,
confirmed identical in `pywinkeyerserial/winkeyerserial/__main__.py`
lines 186-195): it unconditionally sets `self.device`/
`settings_dict["device"]` to whichever port `comports()` enumerates
*last*, with no regard for whether it looks like real hardware.
`comports()`'s ordering is OS-internal and not something the app
controls; a real WinKeyer USB adapter enumerated before a virtual port
(confirmed possible: `/dev/cu.debug-console` and
`/dev/cu.Bluetooth-Incoming-Port` both showed on this machine, description
"n/a", vid `None`, next to `/dev/cu.usbserial-8340` with description
"USB Serial" and vid/pid set) loses the "last wins" arbitration.

**Hypothesis (best-evidence, not certain — no click-by-click trace of
tonight's session was available):** the most likely mechanism requiring
no race or signal misfire at all is that whenever `loadsaved()` writes
sane defaults for a config that doesn't yet exist (`os.path.exists(path)`
false), it writes `self.settings_dict` verbatim — including whatever
arbitrary, possibly-virtual device the enumeration loop just landed on
— with zero user interaction. `comports()` ordering can plausibly vary
run to run (e.g. a Bluetooth device reconnecting/re-registering shifts
where its virtual port lands in the list), so a run where the virtual
port happened to enumerate last would persist it as the "default"
immediately.

A second, lower-confidence contributing gap was found during this
investigation but is **not** fixed here (out of scope per this task's
scope: `host_init()`'s serial-open/reconnect logic is a different
agent's territory): `host_init()`'s
`self.comboBox_device.blockSignals(True)` only suppresses signals
emitted by the `QComboBox` object itself. It does **not** cover the
separate `QLineEdit` object returned by `.lineEdit()` (`setEditable(True)`
puts one there), whose `editingFinished` is wired directly to
`change_serial` in `__init__`. A focus-out on that inner line edit
(plausible during window `show()`, opening the Settings dialog, or any
Qt-internal focus shuffle at startup) fires `editingFinished` unblocked
by the combobox's own `blockSignals`, calling `change_serial()` and
persisting whatever text is currently displayed — which, per the
enumeration-order analysis above, is not necessarily the loaded
`self.device` at all, since nothing syncs the visible selection to it
until `host_init()` runs later in `main()`. Flagging this for whoever
owns `host_init()` next; not exercised or fixed by this change.

**Decision:**
1. Harden auto-selection only (in scope): add `_is_real_serial_port()`,
   preferring `vid is not None` (pyserial's structural USB-vendor-id
   signal, confirmed populated for the one real device and `None` for
   every virtual entry on this machine) with a description-not-"n/a"
   fallback for backends that don't populate `vid`. The enumeration loop
   now tracks the last *real-looking* candidate separately from the last
   *any* candidate, and prefers the former — so a virtual port
   enumerated after a real one can no longer clobber it, while an
   all-virtual or empty port list still falls back to source's original
   "last one wins" behavior (some default beats none, and there's
   nothing to discriminate among virtual-only candidates anyway).
   Manual selection is untouched: every enumerated port, virtual or
   real, still populates the dropdown and remains explicitly pickable.
2. **Saved-but-virtual device: still honored, not overridden.** If
   `loadsaved()` finds an existing saved `"device"` value — even one
   that looks virtual — it is trusted verbatim, exactly as source always
   did. Rationale: the combobox is deliberately editable so a user can
   pick *any* enumerated port on purpose, and there is no way to
   distinguish "a stale bad auto-default from before this fix" from "a
   deliberate advanced/test choice" after the fact — silently
   overriding either would break the explicit-override guarantee this
   same task requires. The narrower, unambiguous case — no `"device"`
   key at all, or an empty one — *does* now fall back to the
   real-hardware-preferring auto pick (`self._auto_default_device`,
   computed once in `__init__`) instead of raising `KeyError` (source's
   literal `self.settings_dict["device"]`) or persisting `""`.
   Root-caused instead of patched over: since the auto-pick itself no
   longer defaults to a virtual port, a *fresh* bad save of this kind
   shouldn't recur; the trust-the-saved-value path stays exactly as
   simple as source's.

**Rejected alternative:** Silently re-run the real-device heuristic over
a saved-but-virtual device on every load and swap it out from under the
user — rejected because it directly contradicts the requirement that
manual selection of a virtual port must keep working, and because there
is no reliable signal to tell a deliberate choice apart from a bad
default after the fact. Also rejected: matching on `/dev/cu.*` name
fragments (e.g. `wchusbserial`, `SLAB_USBtoUART`) as the primary signal
— macOS-specific, doesn't generalize to Linux/Windows naming, and is
strictly weaker evidence than `vid`, which pyserial reports the same way
cross-platform.

## 8. Rule 9 vs a reconnect storm in getwaiting()'s bare-except path

**Rule:** A recoverable condition shouldn't cost more than the feature it
belongs to (§5); mark unverified behavior unverified (rule 9).
**Conflict:** §2 kept source's bare `except:` in `getwaiting()` for parity
— any exception triggers an unconditional `host_init()`. Confirmed live
tonight: two `"... is open but WinKeyer is not responding"` warnings
6 seconds apart from a session that had opened cleanly ~60s earlier, with
no user action in between. That warning only ever prints inside
`host_open()`, only ever reached from `host_init()` — proving `host_init()`
fired repeatedly during otherwise-normal operation. Root cause of the
*storm* (as opposed to the single triggering error) is structural, not
guesswork: if a reopen's `serial.Serial().open()` fails, `host_init()`
sets `self.port = False` and returns *without* restarting `timer2` — but
`timer2` was already running from the prior successful open and keeps
firing every 100ms regardless. The next tick calls `getwaiting()`, which
does `self.port.in_waiting` on a bool, raising `AttributeError`; source's
bare except catches that too and calls `host_init()` again — a tight loop
on a device that may not even be there, gated by nothing. Separately, a
non-blocking read (`timeout=0`) can report `in_waiting > 0` and then have
`read(1)` come back empty by the time it executes; source's `byte[0]`
would raise `IndexError` on that empty result and get the same
misdiagnosis-as-hardware-fault treatment.
**Decision (why the underlying error is plausible, not just the storm):**
Hypothesis, *not confirmed against real hardware in this worktree*
(no live serial access here by design) — one or more of: macOS USB power
management suspending an idle FTDI adapter; the fixed 0.5s post-open
settle time being sized for a cold DTR-reset boot, not a mid-session
reopen where the WinKeyer/bridge may need longer; or a genuine
intermittent USB dropout on hardware that already showed marginal
connections elsewhere tonight (separately fixed). The fix targets the
storm and the misdiagnosis regardless of which of these is the actual
trigger:
1. Narrowed `getwaiting()`'s except to `serial.SerialException` — verified
   against the installed pyserial 3.5 source that its POSIX backend wraps
   every real read/disconnect condition (including "device reports
   readiness to read but returned no data") in `SerialException` or a
   subclass (`PortNotOpenError`, `SerialTimeoutException`), which itself
   subclasses `OSError`; nothing serial-layer is missed, but an unrelated
   app bug (`AttributeError`/`IndexError`/etc.) now surfaces instead of
   being silently relabeled a hardware fault.
2. `self.port` being falsy/not-open is now checked explicitly at the top
   of `getwaiting()` instead of relying on the `AttributeError` it used to
   throw — routed through the same reconnect gate as a caught exception,
   not a special case.
3. An in_waiting-but-empty `read()` now returns early instead of indexing
   into an empty result.
4. Added a reconnect backoff: `_register_reconnect_failure()`/
   `_register_reconnect_success()` track consecutive failures and gate
   further automatic attempts (`_attempt_reconnect()`, called only from
   `getwaiting()`) behind an exponential wait (1s, 2s, 4s, ... capped at
   30s), reset to zero on the first `host_open()` that gets a non-empty
   version response. An explicit/first `host_init()` call (`main()` at
   startup, `change_serial()` from the UI) is never gated — only the
   automatic path is throttled, and re-picking the device in the combo box
   remains an always-available manual override.
5. `host_init(is_reconnect=...)`: a reconnect gets a longer pre-version-read
   settle (1.5s vs. 0.5s) than a first/cold-boot open, on the settle-timing
   hypothesis above.
**Rejected alternative:** Stop retrying permanently after N failures
("port physically gone" hard-stop) — rejected because there is no UI
affordance to signal that or let the operator force a retry beyond
re-picking the device (which already bypasses the gate), so a hard stop
would require watching the log/combo-box to notice the keyer silently
gave up; bounded exponential backoff degrades gracefully instead and
costs nothing once the device is genuinely gone (30s cap, not zero).
**Rejected alternative:** Catch `(serial.SerialException, OSError)` for
extra safety margin across platforms — rejected once the installed
pyserial source showed `SerialException` already subclasses `OSError`
and its POSIX backend never raises a bare unwrapped `OSError` out of
`read()`; adding `OSError` back would have re-widened the catch to
include unrelated errors (e.g. a stray file I/O failure) that rule 9
specifically wants surfaced, not masked.
**Unverified:** the settle-timing lengthening and the USB-power-management/
intermittent-dropout hypotheses are reasoned from the log evidence and
pyserial's source, not confirmed against the operator's WK-mini — this
worktree deliberately does not open `/dev/cu.usbserial-8340` while the
operator has a live session on it. Flagging per rule 9: needs a live
soak-test confirmation before this is treated as closed rather than
mitigated.

## 9. Rule 9 vs a live-confirmed close/reopen race in host_init() (supersedes #8's unverified hypotheses)

**Rule:** Mark unverified behavior unverified, and confirm hypotheses
against real hardware before treating them as closed (rule 9; #8's own
closing note).
**Conflict:** #8 left two competing, unconfirmed hypotheses for the "is
open but WinKeyer is not responding" warning: settle time too short, or
macOS USB power management suspending an idle adapter. Neither was
confirmed live. A live session this time (`troubleshooting-transcript.md`
turns 19-30) reproduced the warning at both startup and after every
device-combo-box reselect, then live testing against the real WK-mini
(port confirmed free via `lsof`, no contention) determined the actual
mechanism:
- `tools/serial_isolation_diagnostic.py` (raw pyserial, no Qt/app code,
  0.5s gap between every close and reopen): 8/8 clean trials, version
  response in ~0.10s every time, across a soak test and a DTR-handling
  sweep (dsrdtr default / no DTR / explicit pulse). This ruled out DTR
  handling and rules out "settle time after open" as the cause — the
  response arrives far inside even the shorter 0.5s window.
- `tools/app_level_repro.py` (drives the real `WinKeyer` class headlessly
  against the same hardware): cold start, 10s idle, and a single
  device-combo-box reselect all came back clean. 15 rapid-fire reselects
  with zero gap between them (mirroring what `host_init()` actually does
  — `self.port.close()` immediately followed by a new `serial.Serial()`
  and `.open()`, no delay) reproduced 4 separate failure episodes in
  ~20s. The one variable that differed between the always-clean isolated
  script and the reliably-failing app-level test was that gap.
- mbridak's upstream source has the identical zero-delay close/reopen
  (confirmed by reading `pywinkeyerserial/winkeyerserial/__main__.py` at
  current HEAD, `632f560`) — this is an inherited bug, not something the
  port introduced. No upstream commit fixes it: `818a0fd` ("Fix
  re-entrant host_init() calls") added the `blockSignals()`/
  `editingFinished` wiring keyer-mac already has, but only guards against
  `setCurrentIndex()` re-firing `currentIndexChanged` during
  `host_init()`, not this timing race; `ce13c9a` (keepalive) solves a
  different problem (idle-timeout session drops, not a reopen race).
**Decision:** Two changes to `host_init()`/`host_open()` in
`keyer_mac/__main__.py`, verified against the exact test that reproduced
the failure (`tools/app_level_repro.py` Phase 5, 15 rapid-fire reselects
— 4 failures before, 0/15 clean across two consecutive runs after):
1. `_close_reopen_settle_s = 0.3`: a pad between `self.port.close()` and
   constructing/opening the new `serial.Serial()`, only when there's a
   previous port to close (not on the first-ever open). Narrows the
   demonstrated race directly.
2. `_host_open_max_attempts = 3` / `_host_open_retry_delay_s = 0.3`:
   `host_open()` retries the WinKeyer-level handshake
   (`_host_open_attempt()`: host_close/sleep/write-open/settle/read)
   rather than re-touching the OS-level port, so a retry can't
   re-trigger the very race it's recovering from. Logging, the on-screen
   message, and `_register_reconnect_failure()`/`_register_reconnect_success()`
   fire once, after the retry loop concludes — not per attempt — so a
   recovered transient miss stays silent.
**Rejected alternative:** A longer fixed settle delay alone (e.g. 1s+,
no retry loop) — rejected because a fixed constant narrows the race's
window but can't guarantee landing outside it every time; the retry loop
is what actually makes a miss invisible instead of merely less frequent.
**Rejected alternative:** Retrying by calling `host_init()` again
(reopening the OS-level port each retry) — rejected because that repeats
the close/reopen race the fix targets on every retry instead of retrying
only the protocol handshake on an already-open port.
**Tradeoff, not yet mitigated:** a genuine hardware failure (device
actually gone) now takes up to ~3x longer to surface — roughly 6-8s
worst case (3 attempts x (~1s host-close wait + 0.5-1.5s settle), plus
two 0.3s retry gaps) versus ~1.5-2.5s before. Accepted because the
alternative was a reproducible false failure on ordinary use; flagged
here per rule 9 rather than left implicit.
**Verified:** live against the real WK-mini on this machine — see
`tools/serial_isolation_diagnostic.py` and `tools/app_level_repro.py`
Phase 5's before/after result above. #8's settle-timing and
USB-power-management hypotheses are superseded, not confirmed — the
actual cause was the close/reopen gap, not open-to-read timing or power
suspend.

## 10. Rule 9 vs a phantom pot line permanently overriding the speed default (supersedes #6's arbitration approach)

**Rule:** Standing Bar — a control that can never actually be used isn't
a control; mark unverified behavior unverified until confirmed (rule 9).
**Conflict:** #6 chose arbitration (track each source's own last value,
ignore a repeated echo) specifically over ignoring the pot outright,
because ignoring it "would silently break live pot control on any WK
unit that has a real, working potentiometer." That was a hedge against
an unconfirmed possibility — this session the operator confirmed
directly this WK-mini has no physical pot at all. Arbitration only
suppresses a *repeated* stale reading; the *first* one after any fresh
`host_init()` still passes through unopposed (`_last_pot_speed` starts
`None`), so the phantom 35 WPM reading silently overwrote the coded
20 WPM default (`self.spinBox_speed.setValue(20)` in `__init__`) on
every startup and every reconnect — confirmed live via
`tools/app_level_repro.py` Phase 3, which printed "current speed: 35"
immediately after a clean `host_init()` with no user interaction.
**Decision:** `getwaiting()`'s pot-status-byte branch now discards the
byte unconditionally (`pass`, matching the existing Status Change
branch) instead of calling `potspeed()`. `potspeed()` and
`_last_pot_speed` are removed outright — dead code once nothing calls
them, per Standing Bars: don't keep a mechanism whose only job was
managing an input this hardware doesn't have. The spinbox (and XMLRPC's
`setspeed`) are now the sole speed-setting mechanism. Verified live:
`spinBox_speed.value()` held at 20 through `host_init()` and 5s of
`getwaiting()` polling against the real WK-mini (previously snapped to
35 within the first poll).
**Rejected alternative:** Keep #6's arbitration and additionally guard
the very first pot reading too (e.g. seed `_last_pot_speed` from the
first byte without applying it) — rejected as unnecessary complexity
now that the hardware is confirmed pot-less; arbitration's whole reason
to exist was "a real pot might be present," which no longer applies to
this operator's unit.
**Not touched:** `main.ui`'s `spinBox_speed` still caps at 35 WPM
(`minimum=5`, `maximum=35`), independent of POTSET's configured 5-55 WPM
hardware range — noted as a pending follow-up in #6, still pending,
unrelated to this fix.
