# CLAUDE.md — /Projects directory-level rules

Applies to every session under ~/Projects. A project's own masterplan
Constitution governs that project's build; this file governs what holds
across all of them. Where they overlap, the masterplan wins inside its own
project.

## Environment Preflight
Checked at the start of each task — run it once per session; skip for
subsequent tasks once it has already been satisfied this session. Gate,
not a step: when it's due, show a pass/fail table and wait for an explicit
go-ahead before proceeding.
- `python3 --version` + interpreter/venv path; required library imports
- `git --version` + `user.name`/`user.email`; `gh --version` + `gh auth status`
  (each its own row, never folded into a soft note)
- `claude` auth; `.gitignore` covers secrets and build artifacts
- PATH for any tool to be invoked; network reachability when relevant

A PATH FAIL is not "not installed" — rule out a stale-shell false negative
first:
- Windows: check `winget list --id <pkg>` and the registry PATH directly.
- macOS: check `brew list <pkg>` (or `ls /usr/local/bin` /
  `/opt/homebrew/bin`) and `echo $PATH` in a fresh shell.
If the tool is already installed, the fix is a new terminal/shell, not a
reinstall. Never proceed on an assumed dependency. Never attempt a fix
needing sudo or re-auth — print the exact command for me to run.

## Gated Steps
Environment setup and anything requiring a real credential (API key, PAT,
OAuth) advance one step at a time: state the single action, wait for real
pasted-back evidence — command output or an explicit go-ahead — before the
next. A stated intention is not evidence. Symmetric whether the step is
mine or yours. A violation restarts at the first gated step; it is not
apologized past.

Everything else, including installs and unauthenticated calls, proceeds
once named. An approved numbered task list governs its own sequencing.

## Scope
- Build and modify only inside the current project. Read across other
  project folders only to answer questions about history or prior notes.
- State the plan and wait before any exploration reading >15 files.

## Git & GitHub
- All repos: `jcarter-labs`, https, private by default. PAT scopes `repo`
  and `workflow`, nothing more.
- New project = `scripts/new-repo.sh <name>` from `~/Projects`; repo name is
  the directory basename. The script is authoritative for its own steps.
- `~/Projects` is itself a git repo with no remote — a subproject git
  command must never land in it.
- Conventional commit prefixes (feat:, fix:, test:, chore:) with a one-line
  rationale, not a diff summary.

## Standing Bars
- Every new piece of logic ships with at least one test.
- Never print, log, or commit API keys, tokens, or `.env` contents.
- A layout claimed to match a reference needs a numeric, re-runnable
  measurement; build one if the project has none.
- Answer questions about project history from git log or on-disk session
  files, never from in-context conversation.

## Style
- Numbered options over prose when a decision is needed; bullet-length by
  default.
- Flag failure points and edge cases, not just the happy path.
- MS-level EE/CS reader — skip basics.
