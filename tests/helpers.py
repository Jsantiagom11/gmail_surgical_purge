from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

from gmail_surgical_purge.demo import DemoMailbox
from gmail_surgical_purge.errors import PurgeError
from gmail_surgical_purge.models import Rule, RulesConfig, Settings, Source

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakeMailbox(DemoMailbox):
    source: Source = "gmail"

    def __init__(self, count: int = 12) -> None:
        super().__init__(count)
        self.messages = {
            key: value.model_copy(update={"labels": ("INBOX",)})
            for key, value in self.messages.items()
        }
        self.email = "owner@example.com"
        self.calls: list[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = []
        self.fail_on_call: int | None = None
        self.crash_after_write = False
        self.query_results: dict[str, tuple[str, ...]] = {}

    def account(self) -> str:
        return self.email

    def iter_ids(self, query: str) -> Iterator[str]:
        for marker, ids in self.query_results.items():
            if marker in query:
                yield from ids
                return
        yield from self.messages

    def modify(
        self,
        message_ids: Sequence[str],
        add_labels: Sequence[str],
        remove_labels: Sequence[str],
    ) -> None:
        self.calls.append((tuple(message_ids), tuple(add_labels), tuple(remove_labels)))
        if len(self.calls) == self.fail_on_call:
            raise PurgeError("Simulated interruption before write")
        super().modify(message_ids, add_labels, remove_labels)
        if self.crash_after_write:
            self.crash_after_write = False
            raise PurgeError("Simulated lost acknowledgement after write")


def configuration(*rules: Rule, batch_size: int = 5) -> RulesConfig:
    return RulesConfig(
        settings=Settings(batch_size=batch_size),
        rules=rules or (Rule(name="archive", query="in:inbox", label="99_ARCHIVE"),),
    )
