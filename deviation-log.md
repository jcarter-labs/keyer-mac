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
