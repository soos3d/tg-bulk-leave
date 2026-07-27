"""Bulk-leave Telegram groups and channels whose title matches a keyword.

SETUP
-----
1. Install:  uv tool install tg-bulk-leave   (or pipx install tg-bulk-leave,
   or pip install tg-bulk-leave into a venv)
2. Get API credentials at https://my.telegram.org -> API development tools
   (create an app, note api_id and api_hash)
3. Export them, or put them in a .env in the directory you run from:
     TG_API_ID=1234567
     TG_API_HASH=your_api_hash
   These are secrets and must never be committed. Exported environment
   variables take precedence over .env if you set both.
4. Configure keywords, either per run:
     tg-bulk-leave --keyword acme --protected "Acme Alumni"
   or persistently in the config file (see `config.example.toml`; the path is
   printed by --help and by the error you get when no keywords are set).
5. Run it. First run asks for your phone number + the login code Telegram
   sends you (in the app, not by SMS - plus your 2FA password if you have
   one). A .session file is created so later runs skip the login. That file
   grants full access to your account - keep it out of version control and
   out of backups.

USAGE
-----
  tg-bulk-leave                       # DRY RUN - lists matches, leaves nothing
  tg-bulk-leave --execute             # actually leaves them
  tg-bulk-leave --execute --limit 5   # leave only the first 5

Always run the dry run first and read the output.
"""

import argparse
import asyncio
import csv
import os
import random
import sys
import tomllib
from datetime import datetime

import platformdirs
from dotenv import find_dotenv, load_dotenv
from telethon import TelegramClient, errors
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.messages import DeleteChatUserRequest
from telethon.tl.types import ChannelForbidden, Chat, ChatForbidden

# ---------------------------------------------------------------- CONFIG ----

APP_NAME = "tg-bulk-leave"

SESSION_NAME = os.environ.get(
    "TG_SESSION",
    os.path.expanduser("~/.config/tg_cleanup/tg_cleanup"),
)

# Keywords and the protected list live in a TOML config file (see
# default_config_path) and/or come from the command line - never in source.
# Matching is a case-insensitive substring test against the chat title; a
# title containing any PROTECTED entry is never left, even on a keyword hit.
CONFIG_FILENAME = "config.toml"
CONFIG_KEYS = ("keywords", "protected")

# Seconds to wait between leaves. Telegram rate-limits aggressively; going
# below ~2s across hundreds of chats will get you a long FloodWait. These are
# deliberately not configurable: lowering them earns multi-hour bans.
DELAY_MIN = 2.5
DELAY_MAX = 5.0

# Telegram can answer a bulk leave with a FloodWait of many hours. Rather than
# silently parking the script for that long, abort above this many seconds.
MAX_FLOOD_WAIT = 300

# Spreadsheets execute cells starting with these characters, and chat titles
# are chosen by strangers. See csv_safe().
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Reports list every chat you belong to, so keep them and the directory
# collecting them owner-only.
REPORT_MODE = 0o600
REPORTS_DIR = "reports"
REPORTS_DIR_MODE = 0o700

# The session is an account-equivalent credential: full access, no login code.
# Neither os.makedirs nor sqlite constrain permissions (both are umask-masked,
# and the common umask 022 yields a world-readable 0644 session), so the modes
# below are applied explicitly. See secure_session_storage().
SESSION_MODE = 0o600
SESSION_DIR_MODE = 0o700
SESSION_EXTENSION = ".session"

# -----------------------------------------------------------------------------


class ConfigError(RuntimeError):
    """Raised when the script is not configured well enough to run."""


class FloodWaitTooLong(RuntimeError):
    """Raised when Telegram asks for a wait longer than we are willing to sit out."""


def default_config_path() -> str:
    """Where the config file lives when --config is not given."""
    return os.path.join(platformdirs.user_config_dir(APP_NAME), CONFIG_FILENAME)


def load_config_file(path: str | None) -> dict:
    """Read keywords/protected from a TOML config file.

    An explicitly requested file must exist; the default location is optional
    (first-time users configure via --keyword before writing any file).
    Unknown keys are rejected rather than ignored: a typo like `keyword =`
    silently matching nothing would defeat the whole point of the config.
    """
    explicit = path is not None
    resolved = path if explicit else default_config_path()

    try:
        with open(resolved, "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        if explicit:
            raise ConfigError(f"Config file not found: {resolved}") from None
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {resolved}: {exc}") from None

    unknown = sorted(set(data) - set(CONFIG_KEYS))
    if unknown:
        raise ConfigError(
            f"Unknown key(s) in {resolved}: {', '.join(unknown)}. "
            f"Valid keys: {', '.join(CONFIG_KEYS)}."
        )
    for key in CONFIG_KEYS:
        value = data.get(key, [])
        if not (isinstance(value, list)
                and all(isinstance(item, str) for item in value)):
            raise ConfigError(f"'{key}' in {resolved} must be a list of strings.")
    return data


def resolve_matching(cli_keywords, cli_protected, file_config) -> tuple[list, list]:
    """Combine command-line flags with the config file.

    --keyword REPLACES the config keywords: when the user names targets
    explicitly, matching anything else would be a surprise. --protected
    EXTENDS the config's protected list: from the command line, protection
    can only grow - a flag must never silently drop a configured safeguard.
    """
    keywords = list(cli_keywords) if cli_keywords else list(file_config.get("keywords", []))
    protected = list(file_config.get("protected", [])) + list(cli_protected or [])

    if not any(keyword.strip() for keyword in keywords):
        raise ConfigError(
            "No keywords configured, so nothing can match. Pass --keyword TEXT "
            f"or create {default_config_path()} (see config.example.toml):\n"
            '  keywords = ["old project"]\n'
            '  protected = ["keep this group"]'
        )
    return keywords, protected


def load_credentials(env=None) -> tuple[int, str]:
    """Read api_id/api_hash from the environment, or explain what is missing."""
    source = os.environ if env is None else env

    raw_id = (source.get("TG_API_ID") or "").strip()
    api_hash = (source.get("TG_API_HASH") or "").strip()

    missing = [name for name, value in
               (("TG_API_ID", raw_id), ("TG_API_HASH", api_hash)) if not value]
    if missing:
        raise ConfigError(
            f"{' and '.join(missing)} not set. Get credentials at "
            "https://my.telegram.org and export them (see SETUP)."
        )

    try:
        api_id = int(raw_id)
    except ValueError:
        # Deliberately does not echo the value - TG_API_HASH sits next to it.
        raise ConfigError("TG_API_ID must be an integer.") from None

    return api_id, api_hash


def matches(title, keywords, protected) -> bool:
    """True when the title hits a keyword and is not on the protected list."""
    text = (title or "").lower()
    if any(p.lower() in text for p in protected if p):
        return False
    return any(k.lower() in text for k in keywords if k)


def classify_entity(entity) -> str:
    """Label a chat entity.

    Legacy chats are checked by type rather than by the absence of channel
    flags: a gigagroup has broadcast=False and megagroup=False, and treating
    it as a legacy group would send its channel id to DeleteChatUserRequest.
    """
    if isinstance(entity, (Chat, ChatForbidden)):
        return "group"
    if getattr(entity, "broadcast", False):
        return "channel"
    if getattr(entity, "gigagroup", False):
        return "gigagroup"
    if getattr(entity, "megagroup", False):
        return "supergroup"
    return "channel"


def kind(dialog) -> str:
    if dialog.is_user:
        return "dm"
    return classify_entity(dialog.entity)


def is_legacy_group(entity) -> bool:
    """Whether leaving this entity needs DeleteChatUserRequest, not LeaveChannelRequest."""
    return isinstance(entity, (Chat, ChatForbidden))


def is_already_left(entity) -> bool:
    """Whether we have already left this chat.

    Telegram keeps a left legacy group in iter_dialogs() - with its history -
    until the conversation itself is deleted, so presence in the dialog list
    says nothing about membership. Without this check a rerun tries to leave
    the same chats again and burns rate limit on guaranteed failures.
    """
    if isinstance(entity, (ChatForbidden, ChannelForbidden)):
        return True
    return bool(getattr(entity, "left", False))


def is_defunct_group(entity) -> bool:
    """Whether this legacy group no longer exists to be left.

    `deactivated` marks a deleted group; `migrated_to` marks one upgraded to a
    supergroup, where the supergroup appears separately in the dialog list and
    holds the real membership. Neither state sets the `left` flag, so without
    this check both are offered as candidates and spend rate limit on a leave
    that cannot succeed. Both fields exist only on Chat - Channel has neither,
    hence the getattr defaults.
    """
    return bool(getattr(entity, "deactivated", False)
                or getattr(entity, "migrated_to", None))


def csv_safe(value) -> str:
    """Neutralise spreadsheet formulas in third-party-controlled text."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_PREFIXES) else text


def wait_after_flood(seconds: int, cap: int = MAX_FLOOD_WAIT) -> int:
    """Seconds to sleep after a FloodWait, or abort if Telegram wants too long."""
    if seconds > cap:
        raise FloodWaitTooLong(
            f"Telegram asked for a {seconds}s wait (cap is {cap}s). "
            "Stopping; rerun later to continue where this left off."
        )
    return seconds + 5


def apply_limit(candidates, limit):
    """Return at most `limit` candidates, without touching the input list."""
    return list(candidates) if limit is None else list(candidates[:limit])


def session_path(session_name: str) -> str:
    """The file Telethon will create for this session name.

    Mirrors telethon.sessions.sqlite, which appends the extension only when it
    is not already present.
    """
    if session_name.endswith(SESSION_EXTENSION):
        return session_name
    return session_name + SESSION_EXTENSION


def secure_session_storage(session_name: str) -> str:
    """Make the session directory and file owner-only, and return the file.

    The file is created here rather than left to Telethon because sqlite keeps
    the permissions of a file that already exists. On a first run, start()
    writes the auth key and then blocks at the phone-code prompt - potentially
    for minutes - so letting sqlite create it at 0644 would leave an
    account-equivalent credential world-readable for that entire window.

    Re-applying the modes on every run also tightens sessions created by
    earlier versions of this script, which had no permission handling at all.
    """
    directory = os.path.dirname(session_name)
    if directory:
        os.makedirs(directory, exist_ok=True)
        # makedirs' own mode argument is masked by the umask; chmod is not.
        os.chmod(directory, SESSION_DIR_MODE)

    path = session_path(session_name)
    # O_CREAT without O_EXCL: an existing session is opened, never truncated.
    os.close(os.open(path, os.O_RDONLY | os.O_CREAT, SESSION_MODE))
    os.chmod(path, SESSION_MODE)
    return path


def open_report(path):
    """Open a CSV for writing with owner-only permissions from the start."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, REPORT_MODE)
    return os.fdopen(fd, "w", newline="", encoding="utf-8")


def report_path(filename: str) -> str:
    """Where a generated report goes: a directory only the owner can list."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.chmod(REPORTS_DIR, REPORTS_DIR_MODE)
    return os.path.join(REPORTS_DIR, filename)


def write_row(writer, dialog, *extra):
    writer.writerow([
        csv_safe(dialog.name),
        kind(dialog),
        dialog.entity.id,
        *(csv_safe(value) for value in extra),
    ])


def write_match_report(candidates, stamp) -> str:
    """Write the list of matched chats and return where it went."""
    path = report_path(f"telegram_matches_{stamp}.csv")
    with open_report(path) as handle:
        writer = csv.writer(handle)
        writer.writerow(["title", "type", "id", "username"])
        for dialog in candidates:
            write_row(writer, dialog,
                      getattr(dialog.entity, "username", "") or "")
    return path


async def leave(client, dialog):
    entity = dialog.entity
    if is_legacy_group(entity):
        await client(DeleteChatUserRequest(chat_id=entity.id, user_id="me"))
    else:
        await client(LeaveChannelRequest(entity))


async def leave_with_retries(client, dialog, attempts=3):
    """Leave a chat, sitting out Telegram's FloodWaits between attempts.

    The loop is deliberately flat. Nesting a retry inside `except FloodWaitError`
    puts the retry's own failure outside the reach of the sibling `except` that
    records per-chat failures, so a late error escaped leave_all and aborted the
    whole run. Raising from one level keeps every outcome catchable.

    A FloodWait on the final attempt propagates as an ordinary failure; only
    FloodWaitTooLong stops the run.
    """
    for attempt in range(1, attempts + 1):
        try:
            await leave(client, dialog)
            return
        except errors.FloodWaitError as exc:
            if attempt == attempts:
                raise
            wait = wait_after_flood(exc.seconds)
            again = " again" if attempt > 1 else ""
            print(f"  ! rate limited{again}, sleeping {wait}s...")
            await asyncio.sleep(wait)


async def scan(client, keywords, protected):
    """Collect the group/channel dialogs matching the keywords.

    Chats already left, and legacy groups that are defunct, still appear in the
    dialog list. They are counted in the total but never offered as candidates.
    """
    candidates, total = [], 0
    async for dialog in client.iter_dialogs():
        if dialog.is_user:
            continue
        total += 1
        if is_already_left(dialog.entity) or is_defunct_group(dialog.entity):
            continue
        if matches(dialog.name, keywords, protected):
            candidates.append(dialog)
    return candidates, total


async def leave_all(client, candidates, log_path):
    """Leave each candidate, recording the outcome as it goes."""
    left, failed = 0, []

    with open_report(log_path) as handle:
        writer = csv.writer(handle)
        writer.writerow(["title", "type", "id", "result"])

        total = len(candidates)
        for i, dialog in enumerate(candidates, 1):
            try:
                await leave_with_retries(client, dialog)
            except FloodWaitTooLong:
                # A RuntimeError subclass, so it must be re-raised before the
                # catch-all below files it as a mere per-chat failure.
                raise
            except Exception as exc:  # noqa: BLE001 - one bad chat must not stop the run
                failed.append((dialog.name, str(exc)))
                write_row(writer, dialog, f"FAILED: {exc}")
                print(f"[{i}/{total}] FAILED: {dialog.name} - {exc}")
            else:
                left += 1
                write_row(writer, dialog, "left")
                print(f"[{i}/{total}] left: {dialog.name}")

            # Flushed every iteration so a crash mid-run leaves a true record.
            handle.flush()
            # The delay spaces out consecutive requests; after the last one
            # there is nothing left to space it from. A failed leave still
            # consumed a request, so it is paced like a successful one.
            if i < total:
                await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    return left, failed


async def connect(api_id, api_hash):
    """Start an authenticated client, keeping its session owner-only."""
    session_file = secure_session_storage(SESSION_NAME)
    client = TelegramClient(SESSION_NAME, api_id, api_hash)
    await client.start()
    # start() may have replaced the file (e.g. an unreadable session); the
    # credential is only on disk from here on, so re-assert the mode.
    os.chmod(session_file, SESSION_MODE)
    return client


def confirmed(targets) -> bool:
    """The last gate before the irreversible part."""
    print(f"\nAbout to LEAVE {len(targets)} chats. This cannot be undone for")
    print("private groups (you'd need a new invite).")
    return input("Type LEAVE to confirm: ").strip() == "LEAVE"


async def run(client, execute: bool, limit, keywords, protected):
    """Scan, report, and - only past the confirmation gate - leave."""
    me = await client.get_me()
    print(f"Logged in as {me.first_name} (@{me.username})\n")

    print(f"Keywords:  {', '.join(keywords)}")
    print(f"Protected: {', '.join(protected) if protected else '(none)'}\n")

    print("Scanning dialogs...")
    candidates, total = await scan(client, keywords, protected)
    print(f"{total} groups/channels found, {len(candidates)} match your keywords.\n")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report = write_match_report(candidates, stamp)
    print(f"Match list written to {report}\n")

    for dialog in candidates:
        print(f"  [{kind(dialog):<10}] {dialog.name}")

    if not execute:
        print("\nDRY RUN - nothing was left.")
        print("Review the list above, adjust keywords/protected, then rerun with --execute")
        return

    targets = apply_limit(candidates, limit)
    if limit is not None:
        print(f"\n--limit {limit}: only the first {len(targets)} will be left.")

    if not confirmed(targets):
        print("Aborted.")
        return

    log = report_path(f"telegram_left_{stamp}.csv")
    try:
        left, failed = await leave_all(client, targets, log)
    except FloodWaitTooLong as exc:
        print(f"\n{exc}")
        sys.exit(1)

    print(f"\nDone. Left {left}, failed {len(failed)}. Log: {log}")
    for name, err in failed:
        print(f"  {name}: {err}")


async def main(execute: bool, limit, keywords, protected):
    api_id, api_hash = load_credentials()
    client = await connect(api_id, api_hash)
    try:
        await run(client, execute, limit, keywords, protected)
    finally:
        # Covers every exit: dry run, refusal, FloodWaitTooLong's SystemExit,
        # and anything unexpected.
        await client.disconnect()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Bulk-leave Telegram groups and channels whose title "
                    "matches a keyword. Dry run by default.",
        epilog=f"Config file: {default_config_path()} "
               "(command-line --keyword replaces its keywords; "
               "--protected adds to its protected list)",
    )
    parser.add_argument("--execute", action="store_true",
                        help="actually leave the chats (default is a dry run)")
    parser.add_argument("--limit", type=int, default=None,
                        help="leave at most N chats - use for a cautious first run")
    parser.add_argument("-k", "--keyword", action="append", dest="keywords",
                        metavar="TEXT", default=None,
                        help="title substring to match (repeatable; replaces "
                             "the config file's keywords)")
    parser.add_argument("-p", "--protected", action="append", dest="protected",
                        metavar="TEXT", default=None,
                        help="title substring that must never be left "
                             "(repeatable; adds to the config file's list)")
    parser.add_argument("--config", default=None, metavar="PATH",
                        help="config file to use instead of the default location")
    return parser.parse_args(argv)


def entrypoint(argv=None) -> None:
    """Console-script entry: parse, configure, run."""
    args = parse_args(argv)

    # Real environment variables win; a .env found from the current directory
    # upward is the fallback for local runs. Loaded here rather than at import
    # so tests stay hermetic.
    load_dotenv(find_dotenv(usecwd=True), override=False)

    try:
        file_config = load_config_file(args.config)
        keywords, protected = resolve_matching(args.keywords, args.protected,
                                               file_config)
        asyncio.run(main(args.execute, args.limit, keywords, protected))
    except ConfigError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    entrypoint()
