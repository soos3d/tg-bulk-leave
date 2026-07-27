# tg-bulk-leave

[![PyPI](https://img.shields.io/pypi/v/tg-bulk-leave)](https://pypi.org/project/tg-bulk-leave/)
[![CI](https://github.com/soos3d/tg-bulk-leave/actions/workflows/ci.yml/badge.svg)](https://github.com/soos3d/tg-bulk-leave/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/tg-bulk-leave)](https://pypi.org/project/tg-bulk-leave/)

Bulk-leave Telegram groups and channels whose title matches a keyword.

Built for the situation where you've accumulated hundreds of chats — partner
groups, deal rooms, airdrop channels, one-off intro chats — and want them gone
without clicking through each one.

> **Leaving is irreversible.** For a private group you'd need a fresh invite to
> get back in. The tool defaults to a dry run and requires an explicit typed
> confirmation before it touches anything.

---

## How it works

```
scan all dialogs  →  title matches a keyword?  →  title matches protected?  →  leave
                              │ no                        │ yes
                              └── skip ───────────────────┴── skip
```

Matching is a **case-insensitive substring** test against the chat title. A chat
is a candidate if *any* keyword appears in its title, unless *any* protected
string does — protection always wins.

DMs are never touched. Everything runs **locally on your machine**: your
session and credentials never leave it.

## Install

Requires Python 3.11+.

```bash
uv tool install tg-bulk-leave        # recommended
# or
pipx install tg-bulk-leave
```

Or run it without installing:

```bash
uvx tg-bulk-leave --keyword acme     # dry run, nothing installed permanently
```

To install from source instead:

```bash
git clone https://github.com/soos3d/tg-bulk-leave && cd tg-bulk-leave
uv tool install .                    # or: pipx install .
```

## Setup

### 1. Get API credentials

Go to [my.telegram.org](https://my.telegram.org) → *API development tools* and
create an app (any title, platform "Desktop" is fine). Note the `api_id` and
`api_hash`.

- The login code arrives **inside the Telegram app**, not by SMS.
- The `api_hash` is a secret and cannot be revoked — treat it like a password.

**Getting a bare "ERROR" on app creation?** This is a known my.telegram.org
issue ([Telethon #4661](https://github.com/LonamiWebs/Telethon/issues/4661)):
turn off any VPN/proxy/custom DNS, use a connection whose IP is in the same
country as your phone number, try another browser or network, and retry later.

### 2. Provide the credentials

Export them, or put them in a `.env` file in the directory you run from
(see `.env.example`; exported variables win over `.env`):

```ini
TG_API_ID=1234567
TG_API_HASH=your_api_hash_here
```

### 3. Configure keywords

Either per run, on the command line:

```bash
tg-bulk-leave --keyword acme --protected "Acme Alumni"
```

or persistently in a TOML config file (see [`config.example.toml`](config.example.toml)):

```toml
keywords  = ["acme", "airdrop"]   # leave chats matching any of these
protected = ["Acme Alumni"]       # ...except these, always
```

The file lives in your platform's config directory — `tg-bulk-leave --help`
prints the exact path (macOS: `~/Library/Application Support/tg-bulk-leave/config.toml`,
Linux: `~/.config/tg-bulk-leave/config.toml`) — or pass `--config PATH`.

Flags and file combine safely: `--keyword` **replaces** the file's keywords for
that run, while `--protected` only ever **adds** protection — a command-line
flag can never drop a safeguard you configured.

## Usage

```bash
# 1. Dry run — lists every match, leaves nothing. Always start here.
tg-bulk-leave

# 2. Cautious first real run — leave only the first 5 matches.
tg-bulk-leave --execute --limit 5

# 3. The real thing.
tg-bulk-leave --execute
```

`--execute` prints the full list, then requires you to type `LEAVE` (exact
case) to proceed. Anything else aborts.

**Read the dry run properly.** Substring matching casts a wide net, and a short
keyword gets swallowed by longer words — `"art"` also matches *Smart Contract
Devs*. Expand the protected list until the dry-run list contains only chats
you're willing to lose, and use `--limit` for your first real run.

### First run

You'll be asked for your phone number and the login code Telegram sends you
(plus your 2FA password, if set). A session file is then written to
`~/.config/tg_cleanup/` (override with `TG_SESSION`) so later runs skip the
login.

## Output

Every run writes timestamped CSVs into `reports/` (created in the directory you
run from), `0600` inside a `0700` directory:

| File | When | Columns |
|---|---|---|
| `reports/telegram_matches_<stamp>.csv` | every run | title, type, id, username |
| `reports/telegram_left_<stamp>.csv` | `--execute` only | title, type, id, result |

The leave log is flushed after every chat, so if the run dies partway you still
have an accurate record of what actually happened.

**Crashed run?** Just rerun it — chats you've already left are skipped.

Note that leaving a group does *not* remove it from your Telegram dialog list;
the conversation and its history stay until you delete it. Membership is
therefore checked explicitly via the `left` flag (and the `ChatForbidden` /
`ChannelForbidden` types), not by absence from the dialog list. Without that
check a rerun would retry every chat you'd already left.

Defunct legacy groups are skipped for the same reason: a deleted group
(`deactivated`) and one upgraded to a supergroup (`migrated_to`) both linger in
the dialog list without setting the `left` flag, and neither can be left — the
supergroup appears separately and holds the real membership.

## Rate limiting

Telegram throttles bulk leaves hard. The tool sleeps a random 2.5–5.0s between
chats and backs off when told to. These delays are deliberately **not
configurable** — lowering them earns a much longer ban.

If Telegram demands a wait longer than the abort cap (300s), the run **aborts**
rather than silently parking for hours — rerun later to continue.

## Security

The Telethon session file is the sensitive artifact here — **it grants full
access to your account with no login code**. It is deliberately stored outside
any repository (`~/.config/tg_cleanup/`) and `*.session` is gitignored. Every
run re-applies `0700` to that directory and `0600` to the session file, so it
stays owner-only whatever your umask is — and an existing world-readable
session from an older version is tightened on the next run. Treat it like a
password; don't sync it or commit it.

Credentials live only in `.env` or the environment, never in source. The
generated CSVs list every chat you belong to, so they're written `0600` and
gitignored too.

Chat titles are attacker-controlled — anyone can name a group `=HYPERLINK(...)`.
Titles are escaped before being written to CSV so they can't execute when you
open the report in a spreadsheet.

## Development

```bash
git clone https://github.com/soos3d/tg-bulk-leave && cd tg-bulk-leave
uv sync --dev

uv run pytest        # coverage gate at 80%, configured in pyproject.toml
uv run ruff check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the safety invariants a change must
not break, and [SECURITY.md](SECURITY.md) for the threat model.

The suite covers the logic that decides *what gets left*: keyword/protected
precedence, config loading and flag semantics, entity classification, the
`DeleteChatUserRequest` vs `LeaveChannelRequest` dispatch, FloodWait backoff
and abort, CSV escaping, file permissions, and the confirmation gate. Tests use
real Telethon entity types rather than stubs, so classification bugs surface.

One subtlety worth knowing if you touch `leave()`: **legacy groups and channels
need different API calls**, and you can't tell them apart by flags. A
*gigagroup* has both `broadcast=False` and `megagroup=False`, so flag-sniffing
misclassifies it as a legacy group and sends a channel id to
`DeleteChatUserRequest` — which can act on an unrelated chat. Dispatch on type
(`isinstance`), and note that `ChatForbidden` / `ChannelForbidden` are *not*
subclasses of `Chat` / `Channel`.

## Roadmap

This project is **free, open source, and local-first** — your session never
leaves your machine, and that stays true.

- **Now:** 0.1.0 is on PyPI. Next up is whatever real use turns up — bug
  reports and rough edges take priority over new features.
- **Later, maybe:** an optional hosted service for *recurring* cleanup (e.g.
  auto-leave groups with no activity for 30+ days), which needs an always-on
  machine. If that ever ships, it will be a separate opt-in product; the CLI
  remains free and fully local. If you'd want such a service, open an issue —
  that's how demand gets measured.

## Requirements

Python 3.11+, [Telethon](https://docs.telethon.dev) 1.44.

## License

[MIT](LICENSE).
