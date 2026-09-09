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
