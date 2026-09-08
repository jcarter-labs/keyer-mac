# dev-environment

Shared Claude Code scaffolding for the `jcarter-labs` account: the
directory-level `CLAUDE.md` rules plus the tooling they reference
(`scripts/new-repo.sh`, `templates/`). One source of truth, cloned as
`~/Projects` on every machine.

## Setting up a new machine

```
cd ~
git clone https://github.com/jcarter-labs/dev-environment.git Projects
```

Project subdirectories (each its own separate git repo, e.g. from
`scripts/new-repo.sh <name>`) live inside `~/Projects` alongside this
repo's files but are not part of its history — this repo tracks only
`CLAUDE.md`, `scripts/`, and `templates/`.

## Keeping machines in sync

Edit `CLAUDE.md` or the scripts on whichever machine, then:

```
git add -A
git commit -m "..."
git push
```

and `git pull` on the other machine. A `git diff` against `origin/main`
shows any drift before it becomes a surprise.

## Platform notes

`CLAUDE.md`'s Environment Preflight and `scripts/new-repo.sh` both branch
on OS where the underlying check differs (Windows: `winget`/registry PATH,
Git Bash's `pwd -W`; macOS/Linux: `brew`, plain `pwd`). Keep both branches
in sync when either one changes.
