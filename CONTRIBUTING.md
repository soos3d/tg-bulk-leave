# Contributing

Bug reports, fixes, and small features are welcome. Before a large change,
open an issue — this tool leaves groups irreversibly, so scope creep has real
consequences.

## Setup

```bash
git clone https://github.com/soos3d/tg-bulk-leave && cd tg-bulk-leave
uv sync --dev

uv run pytest        # coverage gate at 80%; currently ~98%
uv run ruff check
```

CI runs the suite on Python 3.11–3.14 plus `ruff check` and a build smoke test.
There is deliberately **no `ruff format` gate** — several lines in `cli.py` are
hand-wrapped so the rationale for a safety decision reads well. Don't reformat
files you aren't otherwise changing.

`uv.lock` is committed and CI installs with `--locked`, so a dependency change
must include the regenerated lock.

## Tests come first

Write the failing test, then the fix. `tests/test_tg_bulk_leave.py` covers the
logic that decides *what gets left*, and it does so with **real Telethon entity
types** rather than stubs — a `Chat`, a `ChannelForbidden`, an actual gigagroup
`Channel` — so classification bugs surface instead of being mocked away. Keep
it that way. The destructive path uses a `FakeClient`; no test touches the
network.

Several tests are regression tests for defects that shipped: the gigagroup
dispatch, the confirmation gate, the FloodWait retry cases. Don't weaken them
to make a change pass.

## Invariants

**A PR must not change any of these without a failing test that justifies it.**
Each one is here because getting it wrong cost something real.

- **Entity dispatch is type-based, not flag-based.** `is_legacy_group()` uses
  `isinstance(entity, (Chat, ChatForbidden))`. A gigagroup has `broadcast=False`
  *and* `megagroup=False`, so inferring "legacy group" from those flags
  misclassifies it and routes a channel id to `DeleteChatUserRequest` — which
  can act on an entirely unrelated chat. Note that `ChatForbidden` and
  `ChannelForbidden` are **not** subclasses of `Chat`/`Channel`, so all four
  types must be named explicitly.

- **`PROTECTED` is checked before keywords** in `matches()`. A protected title
  always wins. Preserve that precedence.

- **`--keyword` replaces the config's keywords; `--protected` only extends the
  config's protected list.** Naming targets explicitly should not also match
  everything in the config file, and a command-line flag must never silently
  drop a configured safeguard. Both directions are pinned by tests; changing
  them is a behaviour change, not a refactor.

- **Unknown config keys are rejected, not ignored.** A typo like `keyword =`
  silently matching nothing would defeat the point of having a config file.
  "No keywords anywhere" is an actionable `ConfigError`, not a silent no-op.

- **`DELAY_MIN`, `DELAY_MAX` (2.5–5.0s) and `MAX_FLOOD_WAIT` are not
  configurable** via file, flag, or environment, and are never lowered. The
  leave loop is never parallelized. Telegram rate-limits bulk leaves hard, and
  the abort cap exists so the tool never silently parks for hours.

- **`leave_with_retries()` keeps its retry loop flat.** Do not nest a retry
  inside `except FloodWaitError`: an exception raised inside an `except` block
  is not caught by the sibling `except Exception`, so a third FloodWait — or
  any error on a retry — escaped `leave_all()` and killed the whole run.
  Equally, keep `except FloodWaitTooLong: raise` *ahead* of the catch-all in
  `leave_all()`; it subclasses `RuntimeError`, so without that clause a
  deliberate abort gets silently filed as an ordinary per-chat failure.
  One bad chat must never stop the run.

- **`is_already_left()` and `is_defunct_group()` stay separate** — dead is not
  the same as departed. Leaving a chat does *not* remove it from
  `iter_dialogs()`, so presence in the dialog list says nothing about
  membership; membership is read from the `left` flag and the
  `ChatForbidden`/`ChannelForbidden` types. Separately, `deactivated` (deleted)
  and `migrated_to` (upgraded to a supergroup) are `Chat`-only fields and
  *neither sets `left`*, so without that check both get offered as candidates
  and spend rate limit on a leave that cannot succeed. Do not replace either
  with a dialog-list presence check.

- **Chat titles are attacker-controlled.** Anything user-facing or written to
  CSV goes through `csv_safe()` — a group can be named `=HYPERLINK(...)` and a
  spreadsheet will execute it.

- **Use `report_path()` and `open_report()` for every generated file**, never a
  bare `open()`. Reports list every chat the user belongs to and must be `0600`
  inside a `0700` directory. The per-chat log is flushed after every iteration
  so a crash mid-run still leaves an accurate record — keep the flush.

- **Don't drop `secure_session_storage()`** or move the session into the
  working tree. See [SECURITY.md](SECURITY.md) for why the file is pre-created
  and the modes re-applied on every run.

- **The delay between leaves is skipped after the last chat only.** Don't
  extend that skip to failures — a failed leave still consumed a request and
  must be paced.

- **Dry run stays the default, and `--execute` keeps the typed `LEAVE` gate.**

- **Never ship a shared `api_id`/`api_hash`.** Credentials are per-user and
  environment-only. That's a Telegram ToS line, not a preference.

## Commits and PRs

Conventional-commit subjects (`fix:`, `feat:`, `docs:`, `chore:`, `test:`,
`refactor:`). Explain *why* in the body when the change touches anything above.
PRs should describe how you tested; if you ran it against a real account, say
so and say what you left.
