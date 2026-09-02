"""Validated, versioned domain objects. No network dependencies."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import SafetyError

Action = Literal["archive", "trash"]
Source = Literal["gmail", "demo"]
MessageID = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]

SYSTEM_PROTECTIONS = frozenset({"STARRED", "IMPORTANT", "SENT", "DRAFT", "SPAM"})
RESERVED_LABELS = SYSTEM_PROTECTIONS | {"INBOX", "TRASH", "UNREAD", "CHAT"}


def utc_now() -> datetime:
    return datetime.now(UTC)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Rule(FrozenModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    query: str = Field(min_length=1, max_length=4096)
    action: Action = "archive"
    label: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool = True

    @field_validator("query")
    @classmethod
    def valid_query(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("Query must be non-empty and contain no control characters")
        return value.strip()

    @field_validator("label")
    @classmethod
    def valid_label(cls, value: str | None) -> str | None:
        if value is not None and (
            not value.strip()
            or value.upper() in RESERVED_LABELS
            or value.upper().startswith("CATEGORY_")
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError("Destination must be a non-system user label")
        return value

    @model_validator(mode="after")
    def no_trash_destination(self) -> Self:
        if self.action == "trash" and self.label is not None:
            raise ValueError("Trash rules cannot also specify an archive label")
        return self


class Settings(FrozenModel):
    protected_labels: tuple[str, ...] = ("01_ACTION", "02_WAITING", "03_RECORDS")
    excluded_senders: tuple[str, ...] = ()
    max_plan_age_hours: int = Field(default=24, ge=1, le=168)
    batch_size: int = Field(default=250, ge=1, le=1000)
    workers: int = Field(default=4, ge=1, le=8)
    requests_per_second: float = Field(default=20.0, ge=0.5, le=40.0)

    @field_validator("protected_labels", "excluded_senders")
    @classmethod
    def valid_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("Safety entries must be unique")
        if any(not item.strip() or any(ord(char) < 32 for char in item) for item in values):
            raise ValueError("Safety entries must be non-empty without control characters")
        return values


class RulesConfig(FrozenModel):
    schema_version: Literal[1] = 1
    settings: Settings = Field(default_factory=Settings)
    rules: tuple[Rule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_names(self) -> Self:
        names = [rule.name for rule in self.rules]
        if len(names) != len(set(names)):
            raise ValueError("Rule names must be unique")
        if not any(rule.enabled for rule in self.rules):
            raise ValueError("At least one rule must be enabled")
        return self


class Snapshot(FrozenModel):
    id: MessageID
    labels: tuple[str, ...]


class Sample(FrozenModel):
    id: MessageID
    sender: str = ""
    subject: str = ""
    date: str = ""


class LabelProtection(FrozenModel):
    name: str
    id: str


class PlannedRule(FrozenModel):
    rule: Rule
    effective_query: str
    message_ids: tuple[MessageID, ...]
    samples: tuple[Sample, ...] = ()


class PlanPayload(FrozenModel):
    schema_version: Literal[1] = 1
    app_version: str
    source: Source
    created_at: AwareDatetime
    expires_at: AwareDatetime
    account_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    config_sha256: Digest
    settings: Settings
    protected_labels: tuple[LabelProtection, ...]
    rules: tuple[PlannedRule, ...]

    @model_validator(mode="after")
    def validate_contents(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("Plan expiration must be later than creation")
        assigned: set[str] = set()
        names: set[str] = set()
        for item in self.rules:
            if not item.rule.enabled or item.rule.name in names:
                raise ValueError("Plans require enabled rules with unique names")
            names.add(item.rule.name)
            for message_id in item.message_ids:
                if message_id in assigned:
                    raise ValueError("A message cannot have multiple planned actions")
                assigned.add(message_id)
            if any(sample.id not in item.message_ids for sample in item.samples):
                raise ValueError("Sample IDs must belong to their planned rule")
        return self

    @property
    def total(self) -> int:
        return sum(len(item.message_ids) for item in self.rules)

    @property
    def trash_total(self) -> int:
        return sum(len(item.message_ids) for item in self.rules if item.rule.action == "trash")


def model_digest(model: BaseModel) -> str:
    serialized = json.dumps(
        model.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class Plan(FrozenModel):
    payload: PlanPayload
    sha256: Digest

    @classmethod
    def seal(cls, payload: PlanPayload) -> Plan:
        return cls(payload=payload, sha256=model_digest(payload))

    @property
    def confirmation_token(self) -> str:
        return f"APPLY-{self.sha256[:12].upper()}"

    def verify(self) -> None:
        if not hmac.compare_digest(self.sha256, model_digest(self.payload)):
            raise SafetyError("Plan checksum mismatch. Rebuild and review the plan.")


class State(FrozenModel):
    schema_version: Literal[1] = 1
    plan_sha256: Digest
    rule_index: int = Field(default=0, ge=0)
    offset: int = Field(default=0, ge=0)
    applied: int = Field(default=0, ge=0)
    already_done: int = Field(default=0, ge=0)
    skipped_protected: int = Field(default=0, ge=0)
    skipped_missing: int = Field(default=0, ge=0)
    updated_at: AwareDatetime = Field(default_factory=utc_now)
    completed: bool = False

    @property
    def visited(self) -> int:
        return self.applied + self.already_done + self.skipped_protected + self.skipped_missing

    def verify(self, plan: Plan) -> None:
        if self.plan_sha256 != plan.sha256:
            raise SafetyError("Checkpoint belongs to a different plan")
        rules = plan.payload.rules
        if self.rule_index > len(rules):
            raise SafetyError("Invalid checkpoint rule position")
        if self.rule_index == len(rules):
            if self.offset != 0:
                raise SafetyError("Invalid final checkpoint offset")
        elif self.offset > len(rules[self.rule_index].message_ids):
            raise SafetyError("Invalid checkpoint message offset")
        traversed = sum(len(item.message_ids) for item in rules[: self.rule_index]) + self.offset
        if traversed != self.visited or (self.completed and traversed != plan.payload.total):
            raise SafetyError("Checkpoint counters are inconsistent with its position")
