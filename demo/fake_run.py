"""Drive the real CLI against fabricated chats, for the README demo GIF.

The dry run prints the title of every group the account belongs to, so
recording a real session would publish the operator's chat list inside a
binary that cannot later be grepped, rewritten, or scrubbed from history.
Fabricated data is the only safe way to record this.

What makes the recording honest is that *only the client is fake*. This module
replaces `cli.connect()` and then calls the real `cli.entrypoint()`, so
argument parsing, config loading, scanning, matching, reporting, the
confirmation gate, and the leave loop are all the shipped code paths printing
their own output. Nothing here reimplements a print.

Not part of the package, not installed, and never imported by it. Run through
`demo/bin/tg-bulk-leave` so the recording shows the real command name.
"""

import os
import sys
import tempfile
from itertools import islice

from telethon.tl.types import Channel, Chat, User

from tg_bulk_leave import cli

# Fabricated throughout. "acme"/"globex" are the placeholder companies the
# README already uses; no title here corresponds to a real chat.
ACCOUNT_FIRST_NAME = "Sam"
ACCOUNT_USERNAME = "sam_example"

# Chats the dry run should list: enough variety to show every type label, the
# protected list winning, and the two states that are filtered out silently.
MATCHING = (
    ("Acme Partners - Q3", "supergroup"),
    ("Acme Network Announcements", "channel"),
    ("Acme x Globex Deal Room", "supergroup"),
    ("Airdrop Alerts VIP", "channel"),
    ("Acme Devs (legacy)", "group"),
    ("Free Airdrop Signals", "channel"),
    ("Airdrop Farmers United", "gigagroup"),
    ("Acme Hiring 2025", "supergroup"),
    ("Acme Beta Testers", "channel"),
)

# Titles that hit a keyword but must never reach the candidate list. Each one
# exercises a different guard in scan(), and their absence from the printed
# list is the point of showing them.
PROTECTED_TITLE = "Acme Alumni"
ALREADY_LEFT_TITLE = "Acme Support"
DEFUNCT_TITLE = "Acme Old Team"

# Padding so the totals look like the situation the tool is built for -
# hundreds of accumulated chats. These never match and are never printed or
# written to the report, so only the count of them is visible.
FILLER_TITLES = (
    "Rust Users Group", "Design Weekly", "City Cyclists", "Book Club",
    "Neighbourhood Watch", "Photography Chat", "Board Games Night",
    "Home Cooking", "Running Club", "Jazz Records", "Sailing Crew",
    "Woodworking", "Language Exchange", "Film Society", "Chess Ladder",
    "Gardening Tips", "Local Traders", "Hiking Weekends", "Coffee Nerds",
    "Vinyl Swap",
)
FILLER_COUNT = 122


def _channel(entity_id, title, *, broadcast=False, megagroup=False,
             gigagroup=False, left=False):
    return Channel(
        id=entity_id, title=title, photo=None, date=None,
        broadcast=broadcast, megagroup=megagroup, gigagroup=gigagroup,
        left=left,
    )


def _group(entity_id, title, **state):
    return Chat(id=entity_id, title=title, photo=None, participants_count=12,
                date=None, version=1, **state)


def _entity(entity_id, title, label):
    """Build the entity type that classify_entity() will report as `label`."""
    if label == "group":
        return _group(entity_id, title)
    flags = {
        "channel": {"broadcast": True},
        "supergroup": {"megagroup": True},
        "gigagroup": {"gigagroup": True},
    }[label]
    return _channel(entity_id, title, **flags)


class _Dialog:
    """Stand-in for telethon's Dialog: the three attributes cli.py reads."""

    def __init__(self, entity, is_user=False):
        self.entity = entity
        self.is_user = is_user
        self.name = getattr(entity, "title", None) or getattr(
            entity, "first_name", None)


def _dialogs():
    """The fabricated dialog list, in the order Telegram would return it."""
    dialogs = [_Dialog(User(id=1, first_name="Jordan"), is_user=True)]

    for index, (title, label) in enumerate(MATCHING, start=100):
        dialogs.append(_Dialog(_entity(index, title, label)))

    # Hits "acme" but is on the protected list: skipped by matches().
    dialogs.append(_Dialog(_channel(200, PROTECTED_TITLE, megagroup=True)))
    # Left on an earlier run; Telegram still returns it, is_already_left drops it.
    dialogs.append(_Dialog(_channel(201, ALREADY_LEFT_TITLE, broadcast=True,
                                    left=True)))
    # Deleted legacy group: no `left` flag, cannot be left, is_defunct_group drops it.
    dialogs.append(_Dialog(_group(202, DEFUNCT_TITLE, deactivated=True)))

    filler = islice(
        ((index, FILLER_TITLES[index % len(FILLER_TITLES)])
         for index in range(FILLER_COUNT)), FILLER_COUNT)
    for index, title in filler:
        dialogs.append(_Dialog(_channel(1000 + index, title, megagroup=True)))

    return dialogs


class _DemoClient:
    """Answers the four calls cli.py makes on a client. Leaves always succeed."""

    def __init__(self, dialogs):
        self._dialogs = dialogs

    async def get_me(self):
        return User(id=1, first_name=ACCOUNT_FIRST_NAME,
                    username=ACCOUNT_USERNAME)

    async def iter_dialogs(self):
        for dialog in self._dialogs:
            yield dialog

    async def __call__(self, request):
        return None

    async def disconnect(self):
        return None


async def _connect(api_id, api_hash):
    return _DemoClient(_dialogs())


def _sandbox() -> str:
    """A scratch directory to run in, and the fabricated config to run against.

    Running from a temp directory keeps the generated reports out of the repo
    and puts the recording out of reach of a .env in the working tree. The
    config file matters more: --protected only ever *extends* the config's
    protected list, so a real config at the default path would print the
    operator's real protected titles straight into the recording.
    """
    sandbox = tempfile.mkdtemp(prefix="tg-bulk-leave-demo-")
    config = os.path.join(sandbox, "config.toml")
    with open(config, "w", encoding="utf-8") as handle:
        handle.write("keywords = []\nprotected = []\n")
    os.chdir(sandbox)
    return config


def main() -> None:
    config = _sandbox()

    # connect() is the only seam. Everything downstream of it is shipped code.
    cli.connect = _connect

    # load_credentials() runs before the patched connect() and only parses
    # these; no request is ever made with them.
    os.environ["TG_API_ID"] = "1234567"
    os.environ["TG_API_HASH"] = "0" * 32

    cli.entrypoint([*sys.argv[1:], "--config", config])


if __name__ == "__main__":
    main()
