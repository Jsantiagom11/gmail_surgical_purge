"""Synthetic offline demo. No Gmail credentials, messages, or network access."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

from .engine import apply_plan, build_plan
from .models import Rule, RulesConfig, Sample, Settings, Snapshot, Source
from .storage import write_model


class DemoMailbox:
    source: Source = "demo"

    def __init__(self, count: int) -> None:
        self.messages = {
            f"demo_{index:08x}": Snapshot(
                id=f"demo_{index:08x}",
                labels=("INBOX", "STARRED") if index % 100 == 0 else ("INBOX",),
            )
            for index in range(count)
        }
        self.label_map: dict[str, str] = {}
        self.batch_sizes: list[int] = []

    def account(self) -> str:
        return "demo@example.com"

    def labels(self) -> dict[str, str]:
        return dict(self.label_map)

    def iter_ids(self, query: str) -> Iterator[str]:
        # Deliberately not a Gmail query interpreter; this fixture yields the synthetic set.
        yield from self.messages

    def samples(self, message_ids: Sequence[str]) -> tuple[Sample, ...]:
        return tuple(
            Sample(id=message_id, sender="newsletter@example.com", subject="Synthetic demo message")
            for message_id in message_ids
        )

    def snapshots(self, message_ids: Sequence[str]) -> dict[str, Snapshot | None]:
        return {message_id: self.messages.get(message_id) for message_id in message_ids}

    def create_label(self, name: str) -> str:
        if name not in self.label_map:
            self.label_map[name] = f"Label_{len(self.label_map) + 1}"
        return self.label_map[name]

    def modify(
        self,
        message_ids: Sequence[str],
        add_labels: Sequence[str],
        remove_labels: Sequence[str],
    ) -> None:
        self.batch_sizes.append(len(message_ids))
        for message_id in message_ids:
            message = self.messages[message_id]
            labels = (set(message.labels) | set(add_labels)) - set(remove_labels)
            self.messages[message_id] = message.model_copy(update={"labels": tuple(sorted(labels))})


def run_demo(output: Path, count: int) -> dict[str, object]:
    if not 1 <= count <= 200_000:
        raise ValueError("Demo count must be between 1 and 200000")
    mailbox = DemoMailbox(count)
    config = RulesConfig(
        settings=Settings(batch_size=1000),
        rules=(Rule(name="demo_archive", query="label:DEMO", label="99_ARCHIVE"),),
    )
    plan = build_plan(mailbox, config, max_messages=count, sample_size=3)
    write_model(output / "plan.json", plan, overwrite=False)
    state = apply_plan(
        mailbox,
        plan,
        output / "plan.state.json",
        confirmation=plan.confirmation_token,
    )
    return {
        "mode": "SYNTHETIC_OFFLINE_DEMO",
        "network_requests": 0,
        "planned": plan.payload.total,
        "applied": state.applied,
        "protected": state.skipped_protected,
        "mutation_batches": len(mailbox.batch_sizes),
        "largest_batch": max(mailbox.batch_sizes, default=0),
        "completed": state.completed,
    }
