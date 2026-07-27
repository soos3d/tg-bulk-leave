# Demo recording

Everything needed to regenerate `docs/demo.gif`, the animation at the top of
the README. None of it is part of the package; nothing here is installed or
imported by `tg_bulk_leave`.

```bash
brew install vhs        # or see https://github.com/charmbracelet/vhs
uv sync --dev
vhs demo/demo.tape      # from the repository root; writes docs/demo.gif
```

## Why the chats are fake

A dry run prints the title of every group the account belongs to. Recording a
real session would publish that list inside a binary that can't be grepped,
rewritten, or scrubbed out of git history afterwards — a mistake with no clean
undo.

So `fake_run.py` fabricates the chats instead. It builds real Telethon entity
types (`Chat`, `Channel`, `User`) and replaces exactly one thing: `cli.connect()`.
Argument parsing, config loading, scanning, matching, classification,
reporting, the confirmation gate, and the leave loop are all the shipped code
paths printing their own output. Nothing here reimplements a `print`.

That constraint is the point. A demo that formats its own output would drift
from the tool and end up advertising behaviour that no longer exists. **If you
change what the CLI prints, re-record rather than editing the recording.**

`fake_run.py` also runs from a temporary directory with a fabricated
`--config`. Both matter: the generated CSVs stay out of the repository, a
`.env` in the working tree is out of reach, and — because `--protected` only
ever *extends* the config's list — a real config at the default path can't
print the operator's own protected titles into the recording.

## Files

| File | Purpose |
|---|---|
| `fake_run.py` | Fabricated dialogs + patched `connect()`, then the real `entrypoint()` |
| `bin/tg-bulk-leave` | Shim so the recording shows the real command name; on `PATH` only inside the tape |
| `demo.tape` | The vhs script: dry run, then `--execute --limit 3` through the typed `LEAVE` gate |

## Before committing a new recording

Watch the whole thing, frame by frame if need be, and confirm no real chat
title, username, phone number, or file path made it in. The GIF is the one
artifact in this repository that can't be fixed with a follow-up commit.
