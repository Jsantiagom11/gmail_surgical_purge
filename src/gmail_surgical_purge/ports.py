"""Typed boundary between the domain engine and Gmail or a synthetic mailbox."""

from collections.abc import Iterator, Sequence
from typing import Protocol

from .models import Sample, Snapshot, Source


class Mailbox(Protocol):
    @property
    def source(self) -> Source: ...

    def account(self) -> str: ...

    def labels(self) -> dict[str, str]: ...

    def iter_ids(self, query: str) -> Iterator[str]: ...

    def samples(self, message_ids: Sequence[str]) -> tuple[Sample, ...]: ...

    def snapshots(self, message_ids: Sequence[str]) -> dict[str, Snapshot | None]: ...

    def create_label(self, name: str) -> str: ...

    def modify(
        self, message_ids: Sequence[str], add_labels: Sequence[str], remove_labels: Sequence[str]
    ) -> None: ...
