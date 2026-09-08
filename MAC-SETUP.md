# Mac setup

Bringing up a new Mac as a `jcarter-labs` dev machine, using this repo as
`~/Projects`. Each step assumes the previous one is verified before moving
on — paste real output, don't just eyeball it.

## 1. Prerequisites

Install via [Homebrew](https://brew.sh) if not already present:

```
brew install git gh python@3.13
```

- `git` ≥ 2.28 (needed for `git init -b main`, used by `scripts/new-repo.sh`)
- `gh` (GitHub CLI)
- `python@3.13` (matches the Windows machine's toolchain; `scripts/new-repo.sh`
  falls back to plain `python3`/`python` if a versioned binary isn't found,
  but pin 3.13 to stay in sync)
- Claude Code CLI, installed and logged in

Verify:

```
git --version
gh --version
python3.13 --version   # or: python3 --version
claude --version
```

## 2. Git identity

```
git config --global user.name  "John Carter"
git config --global user.email "jcfrgmn@gmail.com"
```

Confirm: `git config user.name` / `git config user.email`.

## 3. GitHub auth

```
gh auth login
```

Choose: GitHub.com → HTTPS → authenticate via browser. Scopes needed:
`repo`, `workflow` (add `delete_repo` too if you want `gh repo delete` to
work from this machine — it's a separate scope GitHub doesn't grant by
default).

Verify: `gh auth status` — should show `jcarter-labs` account, https
protocol, active.

## 4. Clone this repo as `~/Projects`

```
cd ~
git clone https://github.com/jcarter-labs/dev-environment.git Projects
```

This is the same mechanism as any other machine picking up this repo — no
Mac-specific step here. `CLAUDE.md`'s Environment Preflight and
`scripts/new-repo.sh`'s path handling both already branch on OS (see
`README.md`'s Platform notes), so nothing needs editing after clone.

Verify:

```
cd ~/Projects
git rev-parse --show-toplevel   # should print .../Projects
git remote get-url origin       # should print the dev-environment URL
```

## 5. Confirm the script is executable and portable

Git preserves the executable bit and LF line endings across the clone (see
this repo's `.gitattributes`), so this should already work:

```
ls -l scripts/new-repo.sh   # expect -rwxr-xr-x
bash -n scripts/new-repo.sh && echo "syntax OK"
```

If the executable bit didn't survive for some reason: `chmod +x
scripts/new-repo.sh`.

## 6. Live-test with a throwaway project

```
./scripts/new-repo.sh mac-setup-test
```

Expect: directory created at `~/Projects/mac-setup-test`, a Python 3.13
venv, an initial commit, and a private `jcarter-labs/mac-setup-test` repo
on GitHub with that commit pushed. The script prints `OK: ... ready` with
the toplevel/origin/python/venv it verified — paste that output before
trusting the machine for real work.

Clean up afterward:

```
rm -rf ~/Projects/mac-setup-test
gh repo delete jcarter-labs/mac-setup-test --yes   # needs delete_repo scope
```

If `gh repo delete` fails on scope, delete the repo manually at
`https://github.com/jcarter-labs/mac-setup-test/settings`.

## 7. From here

`~/Projects/CLAUDE.md` governs every session under this directory —
Claude Code picks it up automatically. `scripts/new-repo.sh <name>` is the
entry point for every new project. Edits to either should be committed and
pushed from whichever machine made them, and pulled on the other (see
`README.md`'s "Keeping machines in sync").
