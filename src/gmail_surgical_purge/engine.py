"""Deterministic planning and guarded, resumable per-message execution."""

from __future__ import annotations

import hmac
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__
from .config import effective_query
from .errors import GmailAPIError, SafetyError
from .models import (
    SYSTEM_PROTECTIONS,
    LabelProtection,
    Plan,
    PlannedRule,
    PlanPayload,
    RulesConfig,
    State,
    model_digest,
    utc_now,
)
from .ports import Mailbox
from .storage import read_model, write_model

Clock = Callable[[], datetime]


def sample_ids(ids: Sequence[str], size: int) -> tuple[str, ...]:
    if size <= 0 or not ids:
        return ()
    count = min(size, len(ids))
    if count == 1:
        return (ids[0],)
    return tuple(ids[index * (len(ids) - 1) // (count - 1)] for index in range(count))


def build_plan(
    mailbox: Mailbox,
    config: RulesConfig,
    *,
    max_messages: int = 2000,
    sample_size: int = 5,
    clock: Clock = utc_now,
) -> Plan:
    if not 1 <= max_messages <= 1_000_000 or not 0 <= sample_size <= 20:
        raise SafetyError("Invalid planning cap or sample size")
    account = mailbox.account()
    labels = mailbox.labels()
    protections = tuple(
        LabelProtection(name=name, id=labels[name])
        for name in config.settings.protected_labels
        if name in labels
    )
    assigned: set[str] = set()
    planned: list[PlannedRule] = []
    for rule in config.rules:
        if not rule.enabled:
            continue
        query = effective_query(rule, config.settings, set(labels))
        selected: list[str] = []
        for message_id in mailbox.iter_ids(query):
            if message_id in assigned:
                continue
            if len(assigned) >= max_messages:
                raise SafetyError(
                    "Candidate count exceeds --max-messages. Narrow the rules or raise the cap "
                    "explicitly; no partial plan was produced."
                )
            assigned.add(message_id)
            selected.append(message_id)
        samples = mailbox.samples(sample_ids(selected, sample_size))
        planned.append(
            PlannedRule(
                rule=rule,
                effective_query=query,
                message_ids=tuple(selected),
                samples=samples,
            )
        )
    now = clock()
    payload = PlanPayload(
        app_version=__version__,
        source=mailbox.source,
        created_at=now,
        expires_at=now + timedelta(hours=config.settings.max_plan_age_hours),
        account_email=account,
        config_sha256=model_digest(config),
        settings=config.settings,
        protected_labels=protections,
        rules=tuple(planned),
    )
    return Plan.seal(payload)


def check_apply(
    plan: Plan,
    confirmation: str,
    allow_trash: bool,
    now: datetime,
) -> None:
    plan.verify()
    if not hmac.compare_digest(confirmation, plan.confirmation_token):
        raise SafetyError("Confirmation token does not match this plan")
    if plan.payload.trash_total and not allow_trash:
        raise SafetyError("This plan contains Trash actions; --allow-trash is also required")
    if now >= plan.payload.expires_at:
        raise SafetyError("Plan expired. Inspect progress, then build and review a fresh plan.")
    if now < plan.payload.created_at - timedelta(minutes=5):
        raise SafetyError("Plan creation is in the future; check the system clock")


def modify_checked(
    mailbox: Mailbox,
    ids: Sequence[str],
    add: Sequence[str],
) -> tuple[int, int]:
    """Only skip 404s when a fresh metadata read confirms a message disappeared."""
    if not ids:
        return 0, 0
    try:
        mailbox.modify(ids, add, ("INBOX",))
        return len(ids), 0
    except GmailAPIError as exc:
        if exc.status != 404:
            raise
        current = mailbox.snapshots(ids)
        if set(current) != set(ids):
            raise SafetyError("Incomplete metadata response after a rejected batch") from exc
        missing = [message_id for message_id in ids if current[message_id] is None]
        if not missing:
            raise
        remaining = [message_id for message_id in ids if current[message_id] is not None]
        # Do not retry stale eligibility after a concurrent change. Re-enter through apply.
        if remaining:
            raise SafetyError(
                "Mailbox changed while applying a batch. Resume the same plan to revalidate it."
            ) from exc
        return 0, len(missing)


def apply_plan(
    mailbox: Mailbox,
    plan: Plan,
    state_path: Path,
    *,
    confirmation: str,
    allow_trash: bool = False,
    clock: Clock = utc_now,
    progress: Callable[[State], None] | None = None,
) -> State:
    check_apply(plan, confirmation, allow_trash, clock())
    if mailbox.source != plan.payload.source:
        raise SafetyError("Demo and Gmail plans are not interchangeable")
    state = (
        read_model(state_path, State)
        if state_path.exists()
        else State(plan_sha256=plan.sha256, updated_at=clock())
    )
    state.verify(plan)
    if state.completed:
        return state
    if mailbox.account().casefold() != plan.payload.account_email.casefold():
        raise SafetyError("Authenticated account does not match the plan")
    labels = mailbox.labels()
    for protection in plan.payload.protected_labels:
        if labels.get(protection.name) != protection.id:
            raise SafetyError(
                "A protected label was renamed, removed, or replaced; rebuild the plan"
            )
    protected = set(SYSTEM_PROTECTIONS)
    protected.update(item.id for item in plan.payload.protected_labels)
    protected.update(
        labels[name] for name in plan.payload.settings.protected_labels if name in labels
    )

    def checkpoint(value: State) -> State:
        value.verify(plan)
        write_model(state_path, value)
        if progress is not None:
            progress(value)
        return value

    rules = plan.payload.rules
    for index in range(state.rule_index, len(rules)):
        item = rules[index]
        offset = state.offset if index == state.rule_index else 0
        while offset < len(item.message_ids):
            check_apply(plan, confirmation, allow_trash, clock())
            batch = item.message_ids[offset : offset + plan.payload.settings.batch_size]
            snapshots = mailbox.snapshots(batch)
            if set(snapshots) != set(batch):
                raise SafetyError("Incomplete metadata response; batch was not changed")
            eligible: list[str] = []
            already_done = skipped_protected = skipped_missing = 0
            destination = labels.get(item.rule.label) if item.rule.label else None
            for message_id in batch:
                snapshot = snapshots[message_id]
                if snapshot is None:
                    skipped_missing += 1
                    continue
                if snapshot.id != message_id:
                    raise SafetyError("Mismatched metadata response; batch was not changed")
                current_labels = set(snapshot.labels)
                if current_labels.intersection(protected):
                    skipped_protected += 1
                elif "TRASH" in current_labels:
                    if item.rule.action == "trash":
                        already_done += 1
                    else:
                        skipped_protected += 1
                elif (
                    item.rule.action == "archive"
                    and "INBOX" not in current_labels
                    and (item.rule.label is None or destination in current_labels)
                ):
                    already_done += 1
                else:
                    eligible.append(message_id)
            add_labels: tuple[str, ...] = ()
            if eligible:
                if item.rule.action == "trash":
                    add_labels = ("TRASH",)
                elif item.rule.label:
                    if destination is None:
                        destination = mailbox.create_label(item.rule.label)
                        labels[item.rule.label] = destination
                    add_labels = (destination,)
            applied, vanished = modify_checked(mailbox, eligible, add_labels)
            offset += len(batch)
            state = checkpoint(
                state.model_copy(
                    update={
                        "rule_index": index,
                        "offset": offset,
                        "applied": state.applied + applied,
                        "already_done": state.already_done + already_done,
                        "skipped_protected": state.skipped_protected + skipped_protected,
                        "skipped_missing": state.skipped_missing + skipped_missing + vanished,
                        "updated_at": clock(),
                    }
                )
            )
        state = checkpoint(
            state.model_copy(update={"rule_index": index + 1, "offset": 0, "updated_at": clock()})
        )
    return checkpoint(state.model_copy(update={"completed": True, "updated_at": clock()}))
