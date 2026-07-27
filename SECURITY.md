# Security Policy

## Reporting a vulnerability

Use GitHub's **[private vulnerability reporting](https://github.com/soos3d/tg-bulk-leave/security/advisories/new)**
(Security tab → *Report a vulnerability*). Please don't open a public issue for
anything that could expose a user's session or account.

There is no security contact email. The private advisory flow keeps the report
out of public view until a fix ships.

Expect an acknowledgement within a week. This is a small project maintained in
spare time, so there's no SLA beyond a genuine effort to fix real issues promptly
and credit you in the advisory unless you'd rather stay anonymous.

## Supported versions

The latest release on PyPI. There are no maintained release branches; fixes ship
as a new version.

## Threat model

**The Telethon session file is account-equivalent.** It lives at
`~/.config/tg_cleanup/tg_cleanup.session` (override with `TG_SESSION`), and
anyone who copies it gets full access to the account, reading every message and
sending as the user, with **no login code and no further prompt**. Telegram does
not scope MTProto authorizations, so there is no read-only or leave-only
permission to ask for. Treat that file exactly like a password.

**The generated reports enumerate the account's social graph.** Every run writes
`reports/telegram_matches_<stamp>.csv` listing chats the account belongs to.
Group membership can reveal special-category information; a title alone can imply
politics, religion, health, or employer.

**`TG_API_HASH` is a long-lived secret that cannot be revoked.** It comes from
my.telegram.org and identifies the application.

## What the tool does about it

| Risk | Mitigation | Where |
|---|---|---|
| World-readable session | `0700` on the directory and `0600` on the file, re-applied on **every** run, so a session created by an older version gets tightened too | `secure_session_storage()` |
| Session readable during first-run login | The file is pre-created at `0600` before Telethon opens it | `secure_session_storage()` |
| Session inside a repo or backup | Stored under `~/.config/`, never in the working tree; `*.session` is gitignored | `SESSION_NAME` |
| Reports leaking the chat list | Written `0600` inside a `0700` directory, gitignored | `report_path()`, `open_report()` |
| Malicious chat titles | Titles are third-party input; a group can be named `=HYPERLINK(...)` and a spreadsheet will execute it. Titles are escaped before reaching CSV | `csv_safe()` |
| Credentials in source | `TG_API_ID`/`TG_API_HASH` are environment-only; no literal value is ever committed, and error messages never echo the hash | `load_credentials()` |
| Acting on the wrong chat | Entity dispatch is type-based, not flag-based. A gigagroup has `broadcast=False` *and* `megagroup=False`, so flag-sniffing would send a channel id to `DeleteChatUserRequest` | `is_legacy_group()` |

Two details in the permission handling that aren't obvious from the code:

- Neither `os.makedirs` nor sqlite constrain permissions. Both are masked by the
  umask, and the common `umask 022` produced a world-readable `0644` session. The
  modes are therefore applied with an explicit `chmod`.
- The session file is created by this tool rather than left to sqlite, because
  sqlite preserves the mode of a file that already exists. On a first run,
  `start()` writes the auth key and *then* blocks at the phone-code prompt,
  potentially for minutes. That whole window was previously `0644`.

## What you should never do

- **Commit, sync, or back up the session file.** Cloud sync folders, dotfile
  repos, and Time Machine all count. The session-stealer economy prices Telegram
  identities at roughly $400 per thousand.
- **Share `TG_API_HASH`**, or run the tool with someone else's credentials.
- **Run it on a shared or untrusted machine.** Any other account with read access
  to your home directory can take the session.
- **Reuse a session across users.** One session belongs to one account.

If you think a session has been exposed, revoke it immediately in Telegram under
**Settings → Devices → Terminate session**, then delete the local file.

## Out of scope

- **Telegram's own moderation.** Logging in with any third-party client puts an
  account "under observation", and Telegram may rate-limit or restrict it. The
  pacing here (2.5–5.0s between leaves, plus a FloodWait abort cap) is
  deliberately conservative, but no client can guarantee Telegram's behaviour.
  These floors are not configurable; lowering them earns longer bans.
- **Leaving the wrong chat because of a broad keyword.** Matching is a
  case-insensitive substring test. That's why a dry run is the default and
  `--execute` requires typing `LEAVE`. Read the dry-run list.
- **Vulnerabilities in Telethon or Telegram itself.** Report those upstream.
