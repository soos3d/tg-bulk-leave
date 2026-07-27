# tg-bulk-leave — bulk leave Telegram groups by keyword

[![PyPI](https://img.shields.io/pypi/v/tg-bulk-leave)](https://pypi.org/project/tg-bulk-leave/)
[![CI](https://github.com/soos3d/tg-bulk-leave/actions/workflows/ci.yml/badge.svg)](https://github.com/soos3d/tg-bulk-leave/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/tg-bulk-leave)](https://pypi.org/project/tg-bulk-leave/)

Bulk-leave Telegram groups and channels whose title matches a keyword.

![tg-bulk-leave: a dry run listing matches, then a limited run leaving three
chats after a typed confirmation](https://raw.githubusercontent.com/soos3d/tg-bulk-leave/main/docs/demo.gif)

*Recorded against fabricated chats — the pauses between leaves are real.*

Built for the situation where you've accumulated hundreds of chats (partner
groups, deal rooms, airdrop channels, one-off intro chats) and want them gone
without clicking through each one.

> **Leaving is irreversible.** For a private group you'd need a fresh invite to
> get back in. The tool defaults to a dry run and requires an explicit typed
> confirmation before it touches anything.

## Quick start

```bash
# 1. Install (Python 3.11+)
uv tool install tg-bulk-leave

# 2. Credentials from https://my.telegram.org (see Setup below)
export TG_API_ID=1234567 TG_API_HASH=your_api_hash_here

# 3. Dry run. Lists every match, leaves nothing. Always start here.
tg-bulk-leave --keyword acme

# 4. Leave 5 matches to check the behaviour, then the rest.
tg-bulk-leave --keyword acme --execute --limit 5
tg-bulk-leave --keyword acme --execute
```

The first run asks for your phone number and the login code Telegram sends you.
`--execute` prints the full list and waits for you to type `LEAVE` before it
does anything.

## How matching works

A case-insensitive substring test against the chat title:

```
for every chat you're in:
    title contains a protected string?  →  skip
    title contains a keyword?           →  leave
    neither?                            →  skip
```

Protection is checked first and always wins. DMs are never touched, and
everything runs on your machine: your session and credentials never leave it.

## Install

Requires Python 3.11+.

```bash
uv tool install tg-bulk-leave        # recommended
pipx install tg-bulk-leave           # or this
```

Or run it without installing anything permanently:

```bash
uvx tg-bulk-leave --keyword acme
```

From source:

```bash
git clone https://github.com/soos3d/tg-bulk-leave && cd tg-bulk-leave
uv tool install .                    # or: pipx install .
```

## Setup

### 1. Get API credentials

Go to [my.telegram.org](https://my.telegram.org) → *API development tools* and
create an app (any title; platform "Desktop" is fine). Note the `api_id` and
`api_hash`.

- The login code arrives **inside the Telegram app**, not by SMS.
- The `api_hash` is a secret and cannot be revoked. Treat it like a password.

If app creation fails with a bare "ERROR", that's a known my.telegram.org bug
([Telethon #4661](https://github.com/LonamiWebs/Telethon/issues/4661)). Turn off
any VPN, proxy, or custom DNS, use a connection whose IP is in the same country
as your phone number, then try another browser or network and retry later.

### 2. Provide the credentials

Export them, or put them in a `.env` file in the directory you run from (see
`.env.example`). Exported variables win over `.env`.

```ini
TG_API_ID=1234567
TG_API_HASH=your_api_hash_here
```

### 3. Choose keywords

Per run, on the command line:

```bash
tg-bulk-leave --keyword acme --protected "Acme Alumni"
```

Both flags are repeatable and have short forms (`-k`, `-p`).

Or persistently, in a TOML config file (see
[`config.example.toml`](config.example.toml)):

```toml
keywords  = ["acme", "airdrop"]   # leave chats matching any of these
protected = ["Acme Alumni"]       # ...except these, always
```

The file lives in your platform's config directory. Run `tg-bulk-leave --help`
to see the exact path (macOS:
`~/Library/Application Support/tg-bulk-leave/config.toml`, Linux:
`~/.config/tg-bulk-leave/config.toml`), or pass `--config PATH` to use your own.

Flags and file combine safely. `--keyword` **replaces** the file's keywords for
that run, so naming a target explicitly doesn't drag in everything else you've
configured. `--protected` only ever **adds** to the file's list, so a
command-line flag can never drop a safeguard you set up.

A typo in the config (`keyword =` instead of `keywords =`) is rejected with an
error rather than silently matching nothing.

## Running it

Read the dry run properly before you use `--execute`. Substring matching casts
a wide net, and a short keyword gets swallowed by longer words: `"art"` also
matches *Smart Contract Devs*. Expand the protected list until the dry-run list
contains only chats you're willing to lose, and keep `--limit` on for your first
real run.

At the `--execute` prompt, only the exact string `LEAVE` proceeds. Anything else
aborts.

### Logging in

You'll be asked for your phone number and the login code Telegram sends you,
plus your 2FA password if you have one set. The session is then written to
`~/.config/tg_cleanup/` (override with `TG_SESSION`) so later runs skip the
login entirely.

## Reports

Every run writes timestamped CSVs into `reports/`, created in the directory you
run from, mode `0600` inside a `0700` directory:

| File | When | Columns |
|---|---|---|
| `reports/telegram_matches_<stamp>.csv` | every run | title, type, id, username |
| `reports/telegram_left_<stamp>.csv` | `--execute` only | title, type, id, result |

The leave log is flushed after every chat, so a run that dies partway still
leaves an accurate record of what actually happened. If a run crashes, rerun it:
chats you've already left are skipped.

### Why some chats never show up

Leaving a group doesn't remove it from your Telegram dialog list. The
conversation and its history stay until you delete them, so presence in the list
says nothing about membership. Membership is read from the `left` flag and the
`ChatForbidden`/`ChannelForbidden` types instead. Without that check, a rerun
would retry every chat you'd already left.

Defunct legacy groups are dropped for a related reason. A deleted group
(`deactivated`) and one that was upgraded to a supergroup (`migrated_to`) both
linger in the dialog list without setting `left`, and neither can be left. For
the migrated case the supergroup appears separately and holds the real
membership.

## Rate limits

Telegram throttles bulk leaves hard. The tool sleeps a random 2.5–5.0s between
chats and backs off when told to. These delays are deliberately not
configurable; lowering them earns a much longer ban.

If Telegram demands a wait longer than the abort cap (300s), the run aborts
instead of silently parking for hours. Rerun later to continue.

## Security

The Telethon session file is the sensitive artifact here: it grants full access
to your account with no login code. It's stored outside any repository
(`~/.config/tg_cleanup/`), `*.session` is gitignored, and every run re-applies
`0700` to the directory and `0600` to the file, so a world-readable session left
by an older version gets tightened on the next run. Treat it like a password.
Don't sync it, don't commit it.

Credentials live only in `.env` or the environment, never in source. The
generated CSVs list every chat you belong to, so they're written `0600` and
gitignored too.

Chat titles are attacker-controlled: anyone can name a group `=HYPERLINK(...)`.
Titles are escaped before being written to CSV so they can't execute when you
open the report in a spreadsheet.

[SECURITY.md](SECURITY.md) has the full threat model and how to report a
vulnerability.

## Development

```bash
git clone https://github.com/soos3d/tg-bulk-leave && cd tg-bulk-leave
uv sync --dev

uv run pytest        # coverage gate at 80%, configured in pyproject.toml
uv run ruff check
```

The suite covers the logic that decides *what gets left*: keyword/protected
precedence, config loading and flag semantics, entity classification, the
`DeleteChatUserRequest` vs `LeaveChannelRequest` dispatch, FloodWait backoff and
abort, CSV escaping, file permissions, and the confirmation gate. Tests use real
Telethon entity types rather than stubs, so classification bugs surface.

[CONTRIBUTING.md](CONTRIBUTING.md) lists the safety invariants a change must not
break. Read it before touching `cli.py`; several of them exist because getting
it wrong once cost something real.

## Roadmap

This project is free, open source, and local-first. Your session never leaves
your machine, and that stays true.

- **Now:** 0.1.0 is on PyPI. Next up is whatever real use turns up. Bug reports
  and rough edges take priority over new features.
- **Later, maybe:** an optional hosted service for *recurring* cleanup (say,
  auto-leaving groups with no activity for 30+ days), which needs an always-on
  machine. If it ever ships it'll be a separate opt-in product, and the CLI
  stays free and fully local. If you'd want that, open an issue. That's how
  demand gets measured.

## License

[MIT](LICENSE). Built on [Telethon](https://docs.telethon.dev) 1.44.
