"""Tests for the safety-critical pure logic in tg_bulk_leave.

Everything covered here decides *which chats get left*, and leaving a private
group is irreversible. Network calls are deliberately not exercised; the point
is the matching, classification and escaping that guard the destructive call.
"""

import pytest
from telethon import errors
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.messages import DeleteChatUserRequest
from telethon.tl.types import (
    Channel,
    ChannelForbidden,
    Chat,
    ChatForbidden,
    InputChannel,
    User,
)

from tg_bulk_leave import cli as tbl


# ------------------------------------------------------------- helpers ----


def channel(title="c", *, broadcast=False, megagroup=False, gigagroup=False):
    return Channel(
        id=1, title=title, photo=None, date=None,
        broadcast=broadcast, megagroup=megagroup, gigagroup=gigagroup,
    )


def legacy_chat(title="g"):
    return Chat(id=2, title=title, photo=None, participants_count=3,
                date=None, version=1)


def legacy_chat_that_is(title="g", **state):
    """A legacy chat in a terminal state: deactivated= or migrated_to=."""
    return Chat(id=2, title=title, photo=None, participants_count=3,
                date=None, version=1, **state)


class FakeDialog:
    """Minimal stand-in for telethon's Dialog: entity + is_user."""

    def __init__(self, entity, is_user=False):
        self.entity = entity
        self.is_user = is_user
        self.name = getattr(entity, "title", None)


# ------------------------------------------------------------ matches ----


class TestMatches:
    def test_matches_keyword_case_insensitively(self):
        assert tbl.matches("Acme Network Announcements", ["acme"], [])

    def test_no_match_returns_false(self):
        assert not tbl.matches("Rust Users Group", ["acme"], [])

    def test_protected_wins_over_keyword(self):
        assert not tbl.matches("Acme Team", ["acme"], ["Acme Team"])

    def test_protected_is_checked_before_keywords(self):
        """A title matching both lists must be protected, never left."""
        assert not tbl.matches(
            "Globex Alumni Chat", ["globex"], ["Globex Alumni"]
        )

    def test_protected_match_is_case_insensitive(self):
        assert not tbl.matches("ACME TEAM", ["acme"], ["acme team"])

    def test_none_title_does_not_raise(self):
        assert not tbl.matches(None, ["acme"], [])

    def test_empty_keywords_matches_nothing(self):
        assert not tbl.matches("Acme Network", [], [])

    def test_empty_keyword_string_is_ignored(self):
        """A stray '' in KEYWORDS must not make every chat a candidate."""
        assert not tbl.matches("Rust Users Group", [""], [])


# ------------------------------------------------------- classification ----


class TestClassifyEntity:
    def test_broadcast_channel(self):
        assert tbl.classify_entity(channel(broadcast=True)) == "channel"

    def test_megagroup_is_supergroup(self):
        assert tbl.classify_entity(channel(megagroup=True)) == "supergroup"

    def test_legacy_chat_is_group(self):
        assert tbl.classify_entity(legacy_chat()) == "group"

    def test_gigagroup_is_not_classified_as_legacy_group(self):
        """A gigagroup has broadcast=False and megagroup=False.

        Classifying it as a legacy 'group' routes it to DeleteChatUserRequest
        with a channel id, which can act on an unrelated chat.
        """
        assert tbl.classify_entity(channel(gigagroup=True)) == "gigagroup"

    def test_unknown_channel_variant_falls_back_to_channel(self):
        assert tbl.classify_entity(channel()) == "channel"

    def test_forbidden_chat_is_group(self):
        assert tbl.classify_entity(ChatForbidden(id=3, title="x")) == "group"

    def test_forbidden_channel_is_not_a_legacy_group(self):
        ent = ChannelForbidden(id=4, access_hash=0, title="x",
                               broadcast=False, megagroup=False)
        assert tbl.classify_entity(ent) != "group"


class TestKind:
    def test_user_dialog_is_dm(self):
        assert tbl.kind(FakeDialog(User(id=9), is_user=True)) == "dm"

    def test_delegates_to_classify_entity(self):
        assert tbl.kind(FakeDialog(legacy_chat())) == "group"


class TestIsLegacyGroup:
    """Guards the DeleteChatUserRequest vs LeaveChannelRequest dispatch."""

    @pytest.mark.parametrize("entity", [
        legacy_chat(),
        ChatForbidden(id=3, title="x"),
    ])
    def test_true_for_legacy_chats(self, entity):
        assert tbl.is_legacy_group(entity)

    @pytest.mark.parametrize("entity", [
        channel(broadcast=True),
        channel(megagroup=True),
        channel(gigagroup=True),
        channel(),
        ChannelForbidden(id=4, access_hash=0, title="x",
                         broadcast=False, megagroup=False),
    ])
    def test_false_for_every_channel_variant(self, entity):
        assert not tbl.is_legacy_group(entity)


# ----------------------------------------------------------- csv_safe ----


class TestCsvSafe:
    @pytest.mark.parametrize("payload", [
        '=HYPERLINK("http://evil","x")',
        "+1+1",
        "-1+1",
        "@SUM(A1)",
        "\tformula",
        "\rformula",
    ])
    def test_formula_prefixes_are_neutralised(self, payload):
        assert tbl.csv_safe(payload).startswith("'")

    def test_ordinary_titles_are_untouched(self):
        assert tbl.csv_safe("Acme Network") == "Acme Network"

    def test_none_becomes_empty_string(self):
        assert tbl.csv_safe(None) == ""

    def test_non_string_is_coerced(self):
        assert tbl.csv_safe(1234) == "1234"

    def test_title_containing_equals_later_is_untouched(self):
        assert tbl.csv_safe("a=b") == "a=b"


# ------------------------------------------------------- credentials ----


class TestLoadCredentials:
    def test_reads_from_env(self):
        api_id, api_hash = tbl.load_credentials(
            {"TG_API_ID": "12345", "TG_API_HASH": "abc"}
        )
        assert (api_id, api_hash) == (12345, "abc")

    def test_missing_id_raises_actionable_error(self):
        with pytest.raises(tbl.ConfigError, match="TG_API_ID"):
            tbl.load_credentials({"TG_API_HASH": "abc"})

    def test_missing_hash_raises_actionable_error(self):
        with pytest.raises(tbl.ConfigError, match="TG_API_HASH"):
            tbl.load_credentials({"TG_API_ID": "12345"})

    def test_non_numeric_id_raises(self):
        with pytest.raises(tbl.ConfigError, match="TG_API_ID"):
            tbl.load_credentials({"TG_API_ID": "not-a-number",
                                  "TG_API_HASH": "abc"})

    def test_blank_values_are_treated_as_missing(self):
        with pytest.raises(tbl.ConfigError):
            tbl.load_credentials({"TG_API_ID": "  ", "TG_API_HASH": "abc"})

    def test_does_not_mutate_the_env_mapping(self):
        env = {"TG_API_ID": "1", "TG_API_HASH": "h"}
        tbl.load_credentials(env)
        assert env == {"TG_API_ID": "1", "TG_API_HASH": "h"}

    def test_error_message_never_contains_the_hash(self):
        try:
            tbl.load_credentials({"TG_API_ID": "x", "TG_API_HASH": "s3cret"})
        except tbl.ConfigError as exc:
            assert "s3cret" not in str(exc)


# ------------------------------------------------------- flood waiting ----


class TestWaitAfterFlood:
    def test_adds_a_small_buffer(self):
        assert tbl.wait_after_flood(30, cap=300) == 35

    def test_wait_at_the_cap_is_allowed(self):
        assert tbl.wait_after_flood(300, cap=300) == 305

    def test_wait_above_the_cap_aborts_instead_of_sleeping(self):
        """A 24h FloodWait must not silently park the script for a day."""
        with pytest.raises(tbl.FloodWaitTooLong):
            tbl.wait_after_flood(86400, cap=300)

    def test_abort_message_reports_the_requested_wait(self):
        with pytest.raises(tbl.FloodWaitTooLong, match="86400"):
            tbl.wait_after_flood(86400, cap=300)


# ------------------------------------------------------ candidate limit ----


class TestApplyLimit:
    def test_none_limit_keeps_everything(self):
        assert tbl.apply_limit([1, 2, 3], None) == [1, 2, 3]

    def test_limit_truncates(self):
        assert tbl.apply_limit([1, 2, 3], 2) == [1, 2]

    def test_limit_larger_than_input_is_harmless(self):
        assert tbl.apply_limit([1, 2], 10) == [1, 2]

    def test_does_not_mutate_the_input_list(self):
        original = [1, 2, 3]
        tbl.apply_limit(original, 1)
        assert original == [1, 2, 3]

    def test_returns_a_new_list(self):
        original = [1, 2, 3]
        assert tbl.apply_limit(original, None) is not original

# ------------------------------------------------- the destructive path ----


def request_target_title(request):
    """The chat a request is aimed at, as far as a fake client can see."""
    return getattr(getattr(request, "channel", None), "title", None)


class FakeClient:
    """Records the requests it is handed; can be told to fail for a title."""

    def __init__(self, failures=None):
        self.requests = []
        self.failures = {title: list(queue)
                         for title, queue in (failures or {}).items()}

    async def __call__(self, request):
        self.requests.append(request)
        queued = self.failures.get(request_target_title(request))
        if queued:
            raise queued.pop(0)
        return None


def dialog_for(entity):
    return FakeDialog(entity)


def flood(seconds):
    return errors.FloodWaitError(request=None, capture=seconds)


@pytest.fixture
def no_sleep(monkeypatch):
    """Keep tests instant and record what the code tried to sleep for."""
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(tbl.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(tbl, "DELAY_MIN", 0)
    monkeypatch.setattr(tbl, "DELAY_MAX", 0)
    return slept


class TestLeaveDispatch:
    @pytest.mark.asyncio
    async def test_legacy_chat_uses_delete_chat_user(self):
        client = FakeClient()
        await tbl.leave(client, dialog_for(legacy_chat()))
        assert isinstance(client.requests[0], DeleteChatUserRequest)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("entity", [
        channel(broadcast=True),
        channel(megagroup=True),
        channel(gigagroup=True),
        ChannelForbidden(id=4, access_hash=0, title="x",
                         broadcast=False, megagroup=False),
    ])
    async def test_every_channel_variant_uses_leave_channel(self, entity):
        client = FakeClient()
        await tbl.leave(client, dialog_for(entity))
        assert isinstance(client.requests[0], LeaveChannelRequest)

    @pytest.mark.asyncio
    async def test_gigagroup_never_reaches_delete_chat_user(self):
        """The regression that could remove you from an unrelated chat."""
        client = FakeClient()
        await tbl.leave(client, dialog_for(channel(gigagroup=True)))
        assert not any(isinstance(r, DeleteChatUserRequest)
                       for r in client.requests)


class TestLeaveAll:
    @pytest.mark.asyncio
    async def test_leaves_every_candidate(self, tmp_path, no_sleep):
        candidates = [dialog_for(channel(title=f"g{i}", megagroup=True))
                      for i in range(3)]
        left, failed = await tbl.leave_all(
            FakeClient(), candidates, str(tmp_path / "log.csv"))
        assert (left, failed) == (3, [])

    @pytest.mark.asyncio
    async def test_a_failing_chat_does_not_stop_the_run(self, tmp_path, no_sleep):
        client = FakeClient({"bad": [RuntimeError("nope")]})
        candidates = [dialog_for(channel(title=t, megagroup=True))
                      for t in ("good", "bad", "good2")]
        left, failed = await tbl.leave_all(
            client, candidates, str(tmp_path / "log.csv"))
        assert left == 2
        assert [name for name, _ in failed] == ["bad"]

    @pytest.mark.asyncio
    async def test_failure_is_recorded_in_the_log(self, tmp_path, no_sleep):
        log = tmp_path / "log.csv"
        client = FakeClient({"bad": [RuntimeError("nope")]})
        await tbl.leave_all(client, [dialog_for(channel(title="bad",
                                                        megagroup=True))],
                            str(log))
        assert "FAILED: nope" in log.read_text()

    @pytest.mark.asyncio
    async def test_retries_after_a_flood_wait(self, tmp_path, no_sleep):
        client = FakeClient({"g": [flood(30)]})
        left, failed = await tbl.leave_all(
            client, [dialog_for(channel(title="g", megagroup=True))],
            str(tmp_path / "log.csv"))
        assert (left, failed) == (1, [])
        assert 35 in no_sleep

    @pytest.mark.asyncio
    async def test_a_second_flood_wait_backs_off_again_instead_of_failing(
            self, tmp_path, no_sleep):
        """The old code marked this FAILED; waiting again is correct."""
        client = FakeClient({"g": [flood(30), flood(60)]})
        left, failed = await tbl.leave_all(
            client, [dialog_for(channel(title="g", megagroup=True))],
            str(tmp_path / "log.csv"))
        assert (left, failed) == (1, [])
        assert 35 in no_sleep and 65 in no_sleep

    @pytest.mark.asyncio
    async def test_an_overlong_flood_wait_aborts(self, tmp_path, no_sleep):
        """A 24h FloodWait must abort, not park the script for a day."""
        client = FakeClient({"g": [flood(86400)]})
        with pytest.raises(tbl.FloodWaitTooLong):
            await tbl.leave_all(
                client, [dialog_for(channel(title="g", megagroup=True))],
                str(tmp_path / "log.csv"))
        assert 86400 not in no_sleep

    @pytest.mark.asyncio
    async def test_log_escapes_hostile_titles(self, tmp_path, no_sleep):
        log = tmp_path / "log.csv"
        hostile = '=HYPERLINK("http://evil","x")'
        await tbl.leave_all(
            FakeClient(), [dialog_for(channel(title=hostile, megagroup=True))],
            str(log))
        assert "'=HYPERLINK" in log.read_text()

    @pytest.mark.asyncio
    async def test_log_is_owner_only(self, tmp_path, no_sleep):
        import stat
        log = tmp_path / "log.csv"
        await tbl.leave_all(FakeClient(),
                            [dialog_for(channel(megagroup=True))], str(log))
        assert stat.S_IMODE(log.stat().st_mode) == 0o600


class TestPacing:
    @pytest.mark.asyncio
    async def test_no_delay_after_the_last_leave(self, tmp_path, no_sleep):
        """The delay spaces out requests; there is nothing left to space from."""
        candidates = [dialog_for(channel(title=f"g{i}", megagroup=True))
                      for i in range(3)]
        await tbl.leave_all(FakeClient(), candidates,
                            str(tmp_path / "log.csv"))
        assert len(no_sleep) == 2

    @pytest.mark.asyncio
    async def test_a_single_leave_sleeps_not_at_all(self, tmp_path, no_sleep):
        await tbl.leave_all(FakeClient(),
                            [dialog_for(channel(megagroup=True))],
                            str(tmp_path / "log.csv"))
        assert no_sleep == []

    @pytest.mark.asyncio
    async def test_a_failure_still_paces_the_next_attempt(self, tmp_path, no_sleep):
        """A failed leave still consumed a request, so keep the gap."""
        client = FakeClient({"bad": [RuntimeError("nope")]})
        candidates = [dialog_for(channel(title=t, megagroup=True))
                      for t in ("bad", "good")]
        await tbl.leave_all(client, candidates, str(tmp_path / "log.csv"))
        assert len(no_sleep) == 1


class TestRetriesNeverEscape:
    """An exception raised inside an `except` block is not caught by the
    sibling `except Exception`, so retry failures used to kill the whole run.
    """

    @pytest.mark.asyncio
    async def test_exhausted_flood_waits_are_recorded_not_raised(
            self, tmp_path, no_sleep):
        client = FakeClient({"g": [flood(10), flood(10), flood(10)]})
        left, failed = await tbl.leave_all(
            client, [dialog_for(channel(title="g", megagroup=True))],
            str(tmp_path / "log.csv"))
        assert (left, [name for name, _ in failed]) == (0, ["g"])

    @pytest.mark.asyncio
    async def test_an_error_during_retry_does_not_stop_the_run(
            self, tmp_path, no_sleep):
        """One bad chat must not abort the run, even on the retry attempt."""
        client = FakeClient({"bad": [flood(10), RuntimeError("boom")]})
        candidates = [dialog_for(channel(title=t, megagroup=True))
                      for t in ("bad", "good")]
        left, failed = await tbl.leave_all(
            client, candidates, str(tmp_path / "log.csv"))
        assert left == 1
        assert [name for name, _ in failed] == ["bad"]

    @pytest.mark.asyncio
    async def test_an_overlong_wait_still_aborts_from_inside_a_retry(
            self, tmp_path, no_sleep):
        """FloodWaitTooLong subclasses RuntimeError; it must not be swallowed
        by the per-chat `except Exception` that records failures."""
        client = FakeClient({"g": [flood(10), flood(86400)]})
        with pytest.raises(tbl.FloodWaitTooLong):
            await tbl.leave_all(
                client, [dialog_for(channel(title="g", megagroup=True))],
                str(tmp_path / "log.csv"))
        assert 86400 not in no_sleep


class TestScan:
    @pytest.mark.asyncio
    async def test_skips_dms_and_applies_the_protected_list(self):
        dialogs = [
            FakeDialog(User(id=1), is_user=True),
            dialog_for(channel(title="Acme Network", megagroup=True)),
            dialog_for(channel(title="Rust Users", megagroup=True)),
            dialog_for(channel(title="Acme Team", megagroup=True)),
        ]

        class Client:
            def iter_dialogs(self):
                async def gen():
                    for d in dialogs:
                        yield d
                return gen()

        candidates, total = await tbl.scan(Client(), ["acme"],
                                           ["Acme Team"])
        assert total == 3
        assert [d.name for d in candidates] == ["Acme Network"]


# ---------------------------------------------------------- the run gate ----


class FakeTelegramClient:
    """Stands in for TelegramClient across a whole main() run."""

    instances = []

    def __init__(self, session, api_id, api_hash):
        self.session = session
        self.left = []
        self.disconnected = False
        self.dialogs = [
            dialog_for(channel(title="Acme One", megagroup=True)),
            dialog_for(channel(title="Acme Two", megagroup=True)),
            dialog_for(channel(title="Rust Users", megagroup=True)),
        ]
        FakeTelegramClient.instances.append(self)

    async def start(self):
        return self

    async def get_me(self):
        return User(id=1, first_name="Test", username="test")

    def iter_dialogs(self):
        async def gen():
            for d in self.dialogs:
                yield d
        return gen()

    async def __call__(self, request):
        self.left.append(request_target_title(request))

    async def disconnect(self):
        self.disconnected = True


@pytest.fixture
def run_main(monkeypatch, tmp_path, no_sleep):
    """Run main() against a fake Telegram, inside a throwaway cwd."""
    FakeTelegramClient.instances.clear()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tbl, "TelegramClient", FakeTelegramClient)
    # Nested so the run has to create the directory itself, as a real run does.
    monkeypatch.setattr(tbl, "SESSION_NAME", str(tmp_path / "session" / "s"))
    monkeypatch.setenv("TG_API_ID", "1")
    monkeypatch.setenv("TG_API_HASH", "h")

    async def go(execute=False, limit=None, confirm="LEAVE"):
        monkeypatch.setattr("builtins.input", lambda *_: confirm)
        await tbl.main(execute, limit, ["acme"], [])
        return FakeTelegramClient.instances[-1]

    return go


class TestMainGate:
    @pytest.mark.asyncio
    async def test_dry_run_leaves_nothing(self, run_main):
        client = await run_main(execute=False)
        assert client.left == []

    @pytest.mark.asyncio
    async def test_dry_run_still_writes_the_match_report(self, run_main, tmp_path):
        await run_main(execute=False)
        assert list((tmp_path / "reports").glob("telegram_matches_*.csv"))

    @pytest.mark.asyncio
    async def test_reports_are_collected_in_one_directory(self, run_main, tmp_path):
        """Kept out of the working directory, which they used to litter."""
        await run_main(execute=True)
        assert not list(tmp_path.glob("telegram_*.csv"))
        assert len(list((tmp_path / "reports").glob("telegram_*.csv"))) == 2

    @pytest.mark.asyncio
    async def test_the_reports_directory_is_owner_only(self, run_main, tmp_path):
        import stat
        await run_main(execute=False)
        mode = stat.S_IMODE((tmp_path / "reports").stat().st_mode)
        assert mode == 0o700, f"reports dir is {oct(mode)}, not 0o700"

    @pytest.mark.asyncio
    async def test_execute_leaves_the_matches(self, run_main):
        client = await run_main(execute=True)
        assert client.left == ["Acme One", "Acme Two"]

    @pytest.mark.asyncio
    async def test_wrong_confirmation_leaves_nothing(self, run_main):
        client = await run_main(execute=True, confirm="yes")
        assert client.left == []

    @pytest.mark.asyncio
    async def test_confirmation_is_case_sensitive(self, run_main):
        client = await run_main(execute=True, confirm="leave")
        assert client.left == []

    @pytest.mark.asyncio
    async def test_limit_caps_what_is_left(self, run_main):
        client = await run_main(execute=True, limit=1)
        assert client.left == ["Acme One"]

    @pytest.mark.asyncio
    async def test_reports_are_owner_only(self, run_main, tmp_path):
        import stat
        await run_main(execute=True)
        reports = list((tmp_path / "reports").glob("telegram_*.csv"))
        assert reports, "no reports written - the assertion below would be vacuous"
        for report in reports:
            assert stat.S_IMODE(report.stat().st_mode) == 0o600

    @pytest.mark.asyncio
    async def test_disconnects_after_a_dry_run(self, run_main):
        assert (await run_main(execute=False)).disconnected

    @pytest.mark.asyncio
    async def test_disconnects_after_a_real_run(self, run_main):
        assert (await run_main(execute=True)).disconnected

    @pytest.mark.asyncio
    async def test_disconnects_when_the_confirmation_is_refused(self, run_main):
        assert (await run_main(execute=True, confirm="no")).disconnected

    @pytest.mark.asyncio
    async def test_disconnects_even_when_the_run_blows_up(
            self, run_main, monkeypatch):
        """An unexpected error must not leave the connection dangling."""
        async def boom(_client, _keywords, _protected):
            raise RuntimeError("scan exploded")

        monkeypatch.setattr(tbl, "scan", boom)
        with pytest.raises(RuntimeError):
            await run_main(execute=True)
        assert FakeTelegramClient.instances[-1].disconnected

    @pytest.mark.asyncio
    async def test_missing_credentials_abort_before_connecting(
            self, run_main, monkeypatch):
        monkeypatch.delenv("TG_API_ID")
        with pytest.raises(tbl.ConfigError):
            await run_main(execute=True)
        assert not FakeTelegramClient.instances


# ------------------------------------------------- session file secrecy ----


class TestSessionPermissions:
    """The session grants full account access with no login code, so it must
    never be readable by other local users - whatever the ambient umask is.
    """

    @pytest.mark.asyncio
    async def test_session_directory_is_owner_only(self, run_main, tmp_path):
        import stat
        await run_main(execute=False)
        mode = stat.S_IMODE((tmp_path / "session").stat().st_mode)
        assert mode == 0o700, f"session dir is {oct(mode)}, not 0o700"

    @pytest.mark.asyncio
    async def test_session_file_is_owner_only(self, run_main, tmp_path):
        import stat
        await run_main(execute=False)
        mode = stat.S_IMODE((tmp_path / "session" / "s.session").stat().st_mode)
        assert mode == 0o600, f"session file is {oct(mode)}, not 0o600"

    @pytest.mark.asyncio
    async def test_a_world_readable_session_is_tightened(self, run_main, tmp_path):
        """Existing installs already have a 0644 session; fix it on next run."""
        import stat
        session = tmp_path / "session" / "s.session"
        session.parent.mkdir(parents=True)
        session.touch(mode=0o644)
        await run_main(execute=False)
        assert stat.S_IMODE(session.stat().st_mode) == 0o600

    def test_session_path_matches_telethons_extension_rule(self):
        """Telethon appends .session only when it is not already there."""
        assert tbl.session_path("/tmp/s") == "/tmp/s.session"
        assert tbl.session_path("/tmp/s.session") == "/tmp/s.session"


# ------------------------------------------------------ already-left chats ----


class TestIsAlreadyLeft:
    """Telegram keeps left legacy groups in iter_dialogs() until the
    conversation is deleted, so membership must be checked explicitly."""

    def test_chat_with_left_flag(self):
        chat = legacy_chat()
        chat.left = True
        assert tbl.is_already_left(chat)

    def test_channel_with_left_flag(self):
        chan = channel(megagroup=True)
        chan.left = True
        assert tbl.is_already_left(chan)

    def test_forbidden_chat_means_no_longer_a_member(self):
        assert tbl.is_already_left(ChatForbidden(id=3, title="x"))

    def test_forbidden_channel_means_no_longer_a_member(self):
        assert tbl.is_already_left(
            ChannelForbidden(id=4, access_hash=0, title="x",
                             broadcast=False, megagroup=False))

    def test_current_member_chat_is_not_left(self):
        assert not tbl.is_already_left(legacy_chat())

    def test_current_member_channel_is_not_left(self):
        assert not tbl.is_already_left(channel(megagroup=True))


class TestIsDefunctGroup:
    """`deactivated` and `migrated_to` are legacy-Chat-only fields. Neither
    sets the `left` flag, so such a group used to survive the filter and be
    offered as a candidate - a guaranteed-fail leave that burns rate limit.
    """

    def test_deactivated_group_is_defunct(self):
        assert tbl.is_defunct_group(legacy_chat_that_is(deactivated=True))

    def test_migrated_group_is_defunct(self):
        assert tbl.is_defunct_group(
            legacy_chat_that_is(migrated_to=InputChannel(channel_id=9,
                                                         access_hash=0)))

    def test_a_live_legacy_group_is_not_defunct(self):
        assert not tbl.is_defunct_group(legacy_chat())

    def test_a_defunct_group_is_not_reported_as_left(self):
        """The two states are distinct: it is dead, not necessarily departed."""
        assert not tbl.is_already_left(legacy_chat_that_is(deactivated=True))

    @pytest.mark.parametrize("entity", [
        channel(broadcast=True), channel(megagroup=True), channel(gigagroup=True),
    ])
    def test_channels_are_never_defunct(self, entity):
        """Channel carries neither field; getattr must not invent one."""
        assert not tbl.is_defunct_group(entity)


class TestScanSkipsDefunctGroups:
    @pytest.mark.asyncio
    async def test_defunct_groups_are_not_candidates_but_still_counted(self):
        live = channel(title="Globex Live", megagroup=True)
        dead = legacy_chat_that_is(title="Globex Dead", deactivated=True)
        moved = legacy_chat_that_is(
            title="Globex Moved",
            migrated_to=InputChannel(channel_id=9, access_hash=0))
        dialogs = [dialog_for(e) for e in (live, dead, moved)]

        class Client:
            def iter_dialogs(self):
                async def gen():
                    for d in dialogs:
                        yield d
                return gen()

        candidates, total = await tbl.scan(Client(), ["globex"], [])
        assert [d.name for d in candidates] == ["Globex Live"]
        assert total == 3


class TestScanSkipsAlreadyLeft:
    @pytest.mark.asyncio
    async def test_already_left_chats_are_not_candidates(self):
        joined = channel(title="Globex A", megagroup=True)
        already = channel(title="Globex B", megagroup=True)
        already.left = True
        dialogs = [dialog_for(joined), dialog_for(already)]

        class Client:
            def iter_dialogs(self):
                async def gen():
                    for d in dialogs:
                        yield d
                return gen()

        candidates, total = await tbl.scan(Client(), ["globex"], [])
        assert [d.name for d in candidates] == ["Globex A"]

    @pytest.mark.asyncio
    async def test_already_left_chats_still_count_toward_the_total(self):
        """They remain in the account, so the scanned total should include them."""
        already = channel(title="Globex B", megagroup=True)
        already.left = True

        class Client:
            def iter_dialogs(self):
                async def gen():
                    yield dialog_for(already)
                return gen()

        candidates, total = await tbl.scan(Client(), ["globex"], [])
        assert (candidates, total) == ([], 1)


# ------------------------------------------------------- config loading ----


class TestLoadConfigFile:
    """Keywords/protected now live in a TOML file, not in the source."""

    def test_reads_keywords_and_protected(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text('keywords = ["a"]\nprotected = ["b"]\n')
        assert tbl.load_config_file(str(cfg)) == {"keywords": ["a"],
                                                  "protected": ["b"]}

    def test_missing_default_file_is_an_empty_config(self, monkeypatch, tmp_path):
        """First-time users have no file yet; that is not an error."""
        monkeypatch.setattr(tbl, "default_config_path",
                            lambda: str(tmp_path / "nope.toml"))
        assert tbl.load_config_file(None) == {}

    def test_missing_explicit_file_is_an_error(self, tmp_path):
        """A --config the user typed must exist, or they'd get a silent no-op."""
        with pytest.raises(tbl.ConfigError, match="not found"):
            tbl.load_config_file(str(tmp_path / "nope.toml"))

    def test_invalid_toml_reports_the_path(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("keywords = [")
        with pytest.raises(tbl.ConfigError, match="config.toml"):
            tbl.load_config_file(str(cfg))

    def test_a_typoed_key_is_rejected_not_ignored(self, tmp_path):
        """`keyword =` silently matching nothing would defeat the config."""
        cfg = tmp_path / "config.toml"
        cfg.write_text('keyword = ["a"]\n')
        with pytest.raises(tbl.ConfigError, match="keyword"):
            tbl.load_config_file(str(cfg))

    def test_keywords_must_be_a_list(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text('keywords = "a"\n')
        with pytest.raises(tbl.ConfigError, match="list of strings"):
            tbl.load_config_file(str(cfg))

    def test_keyword_items_must_be_strings(self, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text("keywords = [1, 2]\n")
        with pytest.raises(tbl.ConfigError, match="list of strings"):
            tbl.load_config_file(str(cfg))

    def test_default_config_path_is_app_specific(self):
        path = tbl.default_config_path()
        assert path.endswith("config.toml")
        assert "tg-bulk-leave" in path


class TestResolveMatching:
    def test_uses_the_config_file_when_no_flags(self):
        keywords, protected = tbl.resolve_matching(
            None, None, {"keywords": ["a"], "protected": ["b"]})
        assert (keywords, protected) == (["a"], ["b"])

    def test_cli_keywords_replace_config_keywords(self):
        """Explicitly named targets; matching anything else would surprise."""
        keywords, _ = tbl.resolve_matching(["x"], None, {"keywords": ["a"]})
        assert keywords == ["x"]

    def test_cli_protected_extends_config_protected(self):
        """From the command line, protection can only grow - a flag must
        never silently drop a configured safeguard."""
        _, protected = tbl.resolve_matching(["x"], ["extra"],
                                            {"keywords": ["a"],
                                             "protected": ["kept"]})
        assert protected == ["kept", "extra"]

    def test_no_keywords_anywhere_is_an_actionable_error(self):
        with pytest.raises(tbl.ConfigError, match="--keyword"):
            tbl.resolve_matching(None, None, {})

    def test_blank_keywords_are_an_error_not_a_silent_no_op(self):
        with pytest.raises(tbl.ConfigError):
            tbl.resolve_matching(["  "], None, {})


class TestParseArgs:
    def test_default_is_a_dry_run(self):
        args = tbl.parse_args([])
        assert not args.execute
        assert args.limit is None
        assert args.keywords is None and args.protected is None

    def test_keyword_and_protected_flags_are_repeatable(self):
        args = tbl.parse_args(["-k", "a", "--keyword", "b",
                               "-p", "c", "--protected", "d"])
        assert args.keywords == ["a", "b"]
        assert args.protected == ["c", "d"]


class TestEntrypoint:
    def test_config_errors_exit_with_a_message_not_a_traceback(self, tmp_path):
        with pytest.raises(SystemExit, match="not found"):
            tbl.entrypoint(["--config", str(tmp_path / "nope.toml")])

    def test_resolved_config_reaches_main(self, monkeypatch, tmp_path):
        cfg = tmp_path / "config.toml"
        cfg.write_text('keywords = ["a"]\nprotected = ["b"]\n')
        calls = []

        async def fake_main(execute, limit, keywords, protected):
            calls.append((execute, limit, keywords, protected))

        monkeypatch.setattr(tbl, "main", fake_main)
        tbl.entrypoint(["--config", str(cfg), "--limit", "2"])
        assert calls == [(False, 2, ["a"], ["b"])]
