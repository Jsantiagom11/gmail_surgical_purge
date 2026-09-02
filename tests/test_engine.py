from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from gmail_surgical_purge.engine import (
    apply_plan,
    build_plan,
    check_apply,
    modify_checked,
    sample_ids,
)
from gmail_surgical_purge.errors import GmailAPIError, PurgeError, SafetyError
from gmail_surgical_purge.models import Plan, Rule, Snapshot, State
from gmail_surgical_purge.storage import read_model, write_model

from .helpers import NOW, FakeMailbox, configuration


def make_plan(box: FakeMailbox, *rules: Rule) -> Plan:
    return build_plan(box, configuration(*rules), clock=lambda: NOW)


def execute(box: FakeMailbox, plan: Plan, path: Path, *, trash: bool = False) -> State:
    return apply_plan(
        box, plan, path, confirmation=plan.confirmation_token, allow_trash=trash, clock=lambda: NOW
    )


def test_plan_is_read_only_first_match_wins() -> None:
    box = FakeMailbox(10)
    ids = tuple(box.messages)
    box.query_results = {"first": ids[:7] + ids[:2], "second": ids[5:]}
    plan = make_plan(
        box, Rule(name="first", query="first"), Rule(name="second", query="second", action="trash")
    )
    assert [len(item.message_ids) for item in plan.payload.rules] == [7, 3]
    assert plan.payload.total == 10
    assert plan.payload.trash_total == 3
    assert not box.calls and not box.label_map
    assert all("INBOX" in value.labels for value in box.messages.values())


def test_planning_cap_refuses_partial_output() -> None:
    box = FakeMailbox()
    with pytest.raises(SafetyError, match="exceeds"):
        build_plan(box, configuration(), max_messages=5)
    assert not box.calls


@pytest.mark.parametrize(("cap", "sample_size"), [(0, 5), (1_000_001, 5), (12, -1), (12, 21)])
def test_invalid_planning_limits(cap: int, sample_size: int) -> None:
    with pytest.raises(SafetyError):
        build_plan(FakeMailbox(), configuration(), max_messages=cap, sample_size=sample_size)


def test_samples_are_spread_and_bounded() -> None:
    assert sample_ids(tuple(str(i) for i in range(10)), 3) == ("0", "4", "9")
    assert sample_ids(("a", "b"), 1) == ("a",)
    assert sample_ids(("a",), 5) == ("a",)
    assert not sample_ids((), 5)
    assert not sample_ids(("a",), 0)


def test_disabled_rules_omitted() -> None:
    plan = make_plan(
        FakeMailbox(),
        Rule(name="off", query="x", enabled=False, action="trash"),
        Rule(name="on", query="x"),
    )
    assert len(plan.payload.rules) == 1 and not plan.payload.trash_total


def test_plan_digest_roundtrip_and_tamper(tmp_path: Path) -> None:
    plan = make_plan(FakeMailbox())
    path = tmp_path / "plan.json"
    write_model(path, plan)
    assert read_model(path, Plan) == plan
    plan.verify()
    tampered = plan.model_copy(update={"sha256": "0" * 64})
    with pytest.raises(SafetyError, match="checksum"):
        tampered.verify()


def test_confirmation_expiration_and_future_clock() -> None:
    plan = make_plan(FakeMailbox())
    with pytest.raises(SafetyError, match="Confirmation"):
        check_apply(plan, "WRONG", False, NOW)
    with pytest.raises(SafetyError, match="expired"):
        check_apply(plan, plan.confirmation_token, False, NOW + timedelta(days=1))
    with pytest.raises(SafetyError, match="future"):
        check_apply(plan, plan.confirmation_token, False, NOW - timedelta(minutes=6))


def test_trash_requires_second_opt_in(tmp_path: Path) -> None:
    box = FakeMailbox()
    plan = make_plan(box, Rule(name="trash", query="x", action="trash"))
    with pytest.raises(SafetyError, match="allow-trash"):
        execute(box, plan, tmp_path / "state.json")
    assert not box.calls
    state = execute(box, plan, tmp_path / "state.json", trash=True)
    assert state.applied == 12
    assert all("TRASH" in item.labels for item in box.messages.values())
    assert all(call[1:] == (("TRASH",), ("INBOX",)) for call in box.calls)


def test_wrong_account_and_demo_source_rejected(tmp_path: Path) -> None:
    box = FakeMailbox()
    plan = make_plan(box)
    box.email = "another@example.com"
    with pytest.raises(SafetyError, match="account"):
        execute(box, plan, tmp_path / "state.json")
    box.source = "demo"
    with pytest.raises(SafetyError, match="interchangeable"):
        execute(box, plan, tmp_path / "state.json")
    assert not box.calls and not box.label_map


def test_protected_label_rename_fails_closed(tmp_path: Path) -> None:
    box = FakeMailbox()
    box.label_map["01_ACTION"] = "Label_keep"
    plan = make_plan(box)
    box.label_map["01_ACTION"] = "Label_replacement"
    with pytest.raises(SafetyError, match="protected label"):
        execute(box, plan, tmp_path / "state.json")
    assert not box.calls


@pytest.mark.parametrize("label", ["STARRED", "IMPORTANT", "SENT", "DRAFT", "SPAM", "Label_keep"])
def test_current_protections_rechecked(label: str, tmp_path: Path) -> None:
    box = FakeMailbox(1)
    plan = make_plan(box)
    box.label_map["01_ACTION"] = "Label_keep"
    message_id = next(iter(box.messages))
    box.messages[message_id] = Snapshot(id=message_id, labels=("INBOX", label))
    state = execute(box, plan, tmp_path / "state.json")
    assert state.skipped_protected == 1 and not box.calls
    assert "99_ARCHIVE" not in box.label_map


def test_missing_messages_and_already_trashed(tmp_path: Path) -> None:
    box = FakeMailbox(3)
    plan = make_plan(box, Rule(name="trash", query="x", action="trash"))
    ids = tuple(box.messages)
    del box.messages[ids[0]]
    box.messages[ids[1]] = Snapshot(id=ids[1], labels=("TRASH",))
    state = execute(box, plan, tmp_path / "state.json", trash=True)
    assert (state.skipped_missing, state.already_done, state.applied) == (1, 1, 1)


def test_archive_never_restores_trash(tmp_path: Path) -> None:
    box = FakeMailbox(1)
    plan = make_plan(box)
    message_id = next(iter(box.messages))
    box.messages[message_id] = Snapshot(id=message_id, labels=("TRASH",))
    state = execute(box, plan, tmp_path / "state.json")
    assert state.skipped_protected == 1 and not box.calls


def test_checkpoint_resume_after_interruption(tmp_path: Path) -> None:
    box = FakeMailbox(12)
    plan = make_plan(box)
    path = tmp_path / "state.json"
    box.fail_on_call = 2
    with pytest.raises(PurgeError):
        execute(box, plan, path)
    assert read_model(path, State).applied == 5
    first = box.calls[0][0]
    box.fail_on_call = None
    state = execute(box, plan, path)
    assert state.completed and state.applied == 12
    assert not set(first).intersection(
        message_id for call in box.calls[2:] for message_id in call[0]
    )
    calls = len(box.calls)
    assert execute(box, plan, path) == state
    assert len(box.calls) == calls


def test_uncertain_write_replayed_idempotently(tmp_path: Path) -> None:
    box = FakeMailbox(12)
    plan = make_plan(box)
    path = tmp_path / "state.json"
    box.crash_after_write = True
    with pytest.raises(PurgeError):
        execute(box, plan, path)
    assert not path.exists()
    state = execute(box, plan, path)
    assert state.applied == 7 and state.already_done == 5 and state.visited == 12


def test_missing_metadata_is_not_silently_accepted(tmp_path: Path) -> None:
    box = FakeMailbox(1)
    plan = make_plan(box)
    with (
        patch.object(box, "snapshots", return_value={}),
        pytest.raises(SafetyError, match="Incomplete"),
    ):
        execute(box, plan, tmp_path / "state.json")
    message_id = next(iter(box.messages))
    with (
        patch.object(box, "snapshots", return_value={message_id: Snapshot(id="wrong", labels=())}),
        pytest.raises(SafetyError, match="Mismatched"),
    ):
        execute(box, plan, tmp_path / "state.json")


def test_archive_without_destination_and_empty_plan(tmp_path: Path) -> None:
    box = FakeMailbox(1)
    plan = make_plan(box, Rule(name="archive", query="x"))
    state = execute(box, plan, tmp_path / "plain.json")
    assert state.applied == 1 and box.calls[0][1] == ()
    empty_box = FakeMailbox(0)
    empty_plan = make_plan(empty_box)
    empty_state = execute(empty_box, empty_plan, tmp_path / "empty.json")
    assert empty_state.completed and empty_state.visited == 0


def test_state_corruption_is_rejected(tmp_path: Path) -> None:
    box = FakeMailbox()
    plan = make_plan(box)
    path = tmp_path / "state.json"
    write_model(path, State(plan_sha256="0" * 64))
    with pytest.raises(SafetyError, match="different plan"):
        execute(box, plan, path)
    bad_states = [
        State(plan_sha256=plan.sha256, rule_index=99),
        State(plan_sha256=plan.sha256, rule_index=1, offset=1),
        State(plan_sha256=plan.sha256, offset=99),
        State(plan_sha256=plan.sha256, offset=1),
        State(plan_sha256=plan.sha256, completed=True),
    ]
    for state in bad_states:
        with pytest.raises(SafetyError):
            state.verify(plan)


def test_modify_errors_are_not_misclassified_as_missing() -> None:
    box = FakeMailbox(1)
    ids = tuple(box.messages)
    for code in (400, 403, 404):
        with (
            patch.object(box, "modify", side_effect=GmailAPIError(code)),
            pytest.raises(GmailAPIError),
        ):
            modify_checked(box, ids, ("TRASH",))
    assert modify_checked(box, (), ()) == (0, 0)


def test_404_skip_only_when_missing_is_confirmed() -> None:
    box = FakeMailbox(2)
    ids = tuple(box.messages)
    with patch.object(box, "modify", side_effect=GmailAPIError(404)):
        with (
            patch.object(box, "snapshots", return_value={}),
            pytest.raises(SafetyError, match="Incomplete"),
        ):
            modify_checked(box, ids, ("TRASH",))
        del box.messages[ids[0]]
        with pytest.raises(SafetyError, match="changed"):
            modify_checked(box, ids, ("TRASH",))
        del box.messages[ids[1]]
        assert modify_checked(box, ids, ("TRASH",)) == (0, 2)


def test_plan_expires_between_batches(tmp_path: Path) -> None:
    box = FakeMailbox()
    plan = make_plan(box)
    ticks = iter([NOW, NOW, NOW, NOW, NOW + timedelta(days=2)])
    last = NOW

    def clock() -> datetime:
        nonlocal last
        last = next(ticks, last)
        return last

    with pytest.raises(SafetyError, match="expired"):
        apply_plan(
            box, plan, tmp_path / "state.json", confirmation=plan.confirmation_token, clock=clock
        )
    assert read_model(tmp_path / "state.json", State).applied == 5


def test_multi_rule_resume(tmp_path: Path) -> None:
    box = FakeMailbox(8)
    ids = tuple(box.messages)
    box.query_results = {"first": ids[:4], "second": ids[4:]}
    plan = make_plan(box, Rule(name="first", query="first"), Rule(name="second", query="second"))
    state = execute(box, plan, tmp_path / "state.json")
    assert state.applied == 8 and state.rule_index == 2


def test_10001_messages_processed_in_bounded_batches(tmp_path: Path) -> None:
    box = FakeMailbox(10001)
    plan = build_plan(box, configuration(batch_size=1000), max_messages=11000, clock=lambda: NOW)
    state = execute(box, plan, tmp_path / "state.json")
    assert state.applied == 10001
    assert len(box.calls) == 11
    assert max(len(call[0]) for call in box.calls) == 1000


def test_no_permanent_delete_is_exposed() -> None:
    assert not hasattr(FakeMailbox, "delete")
    assert not hasattr(FakeMailbox, "batch_delete")


def test_replay_without_destination(tmp_path: Path) -> None:
    box = FakeMailbox(1)
    plan = make_plan(box, Rule(name="plain", query="x"))
    message_id = next(iter(box.messages))
    box.messages[message_id] = Snapshot(id=message_id, labels=())
    assert execute(box, plan, tmp_path / "state.json").already_done == 1


def test_guarded_ids_are_never_sent_to_modify(tmp_path: Path) -> None:
    box = FakeMailbox(6)
    plan = make_plan(box)
    ids = tuple(box.messages)
    for message_id in ids[::2]:
        box.messages[message_id] = Snapshot(id=message_id, labels=("INBOX", "STARRED"))
    execute(box, plan, tmp_path / "state.json")
    written: Sequence[str] = tuple(message_id for call in box.calls for message_id in call[0])
    assert set(written) == set(ids[1::2])
