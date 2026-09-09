# Mac setup — keyer-mac

Bringing up a dev environment for keyer-mac on a Mac. Each step assumes
the previous one is verified before moving on — paste real output, don't
just eyeball it.

## 1. Prerequisites

Install via [Homebrew](https://brew.sh) if not already present:

```
brew install git gh python@3.13
```

- `git` and `gh` (GitHub CLI), authenticated to the `jcarter-labs` account
  per `~/Projects/CLAUDE.md`'s Environment Preflight
- `python@3.13` (Spec §1 target: Python 3.13+)
- Claude Code CLI, installed and logged in

Verify:

```
git --version
gh --version
gh auth status
python3.13 --version   # or: python3 --version
claude --version
```

## 2. Clone this repo

```
cd ~/Projects
git clone git@github.com:jcarter-labs/keyer-mac.git
```

(Already present if you're reading this from an existing checkout.)

## 3. Create the venv and install dependencies

```
cd ~/Projects/keyer-mac
python3.13 -m venv .venv
source .venv/bin/activate
pip install PyQt6 pyserial
```

Verify:

```
source .venv/bin/activate
python3 --version              # expect 3.13.x
python3 -c "import PyQt6; import serial; print('PyQt6 + pySerial OK')"
```

Pinned versions land in `requirements.txt`/`requirements-lock.txt` once
Task 3 (core logic port) is underway — see `masterplan-seed.md` Tech §2.

## 4. K1EL WinKeyer hardware (when connecting)

Spec §3 targets a USB/serial K1EL WinKeyer at a macOS device path (e.g.
`/dev/cu.usbserial-*`, not the Linux-style `/dev/ttyUSB0` the source
project uses). List candidate devices:

```
ls /dev/cu.*
```

Task 2 (external interfaces / live diagnostic) is deferred until the
device is physically connected — see `masterplan-seed.md` Tasks.

## 5. Reference clone (build reference only, not part of this repo)

`pywinkeyerserial/` is a clone of
[mbridak/PyWinKeyerSerial](https://github.com/mbridak/PyWinKeyerSerial),
kept alongside this project purely as a build reference (see `README.md`
and `masterplan-seed.md`). It's excluded in `.gitignore` and is never
part of keyer-mac's own history:

```
git clone https://github.com/mbridak/PyWinKeyerSerial.git pywinkeyerserial
```

## 6. From here

`masterplan-seed.md` governs the build (Constitution, Spec, Tech, Tasks).
`deviation-log.md` records every place this port deviates from source.
Config at runtime lives at `~/.keyer-mac.json`, matching the source's
dotfile approach.
