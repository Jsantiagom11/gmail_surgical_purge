from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from gmail_surgical_purge.config import effective_query, load_config, quote_term
from gmail_surgical_purge.engine import build_plan
from gmail_surgical_purge.errors import PurgeError, SafetyError
from gmail_surgical_purge.models import (
    Plan,
    PlanPayload,
    Rule,
    RulesConfig,
    Sample,
    Settings,
    model_digest,
)
from gmail_surgical_purge.storage import (
    MAX_ARTIFACT_BYTES,
    exclusive_lock,
    read_model,
    write_model,
    write_private_text,
)

from .helpers import NOW, FakeMailbox, configuration


@pytest.mark.parametrize("query", ["", "  ", "in:inbox\nOR in:sent"])
def test_invalid_queries(query: str) -> None:
    with pytest.raises(ValidationError):
        Rule(name="test", query=query)


@pytest.mark.parametrize("label", ["INBOX", "trash", "CATEGORY_PROMOTIONS", "\n", "  "])
def test_system_or_invalid_destination_rejected(label: str) -> None:
    with pytest.raises(ValidationError):
        Rule(name="test", query="x", label=label)


def test_rule_and_settings_validation() -> None:
    with pytest.raises(ValidationError):
        Rule(name="test", query="x", action="trash", label="archive")
    with pytest.raises(ValidationError):
        RulesConfig(rules=(Rule(name="same", query="a"), Rule(name="same", query="b")))
    with pytest.raises(ValidationError):
        RulesConfig(rules=(Rule(name="disabled", query="a", enabled=False),))
    with pytest.raises(ValidationError):
        Settings(batch_size=1001)
    with pytest.raises(ValidationError):
        Settings(protected_labels=("keep", "keep"))
    with pytest.raises(ValidationError):
        Settings(excluded_senders=(" ",))
    with pytest.raises(ValidationError):
        Rule.model_validate_json('{"name":"rule","query":"x","permanent_delete":true}')
    assert Rule(name="test", query="  in:inbox  ").query == "in:inbox"


def test_example_configuration_is_archive_only() -> None:
    path = Path(__file__).resolve().parents[1] / "config" / "rules.example.toml"
    config = load_config(path)
    assert all(rule.action == "archive" for rule in config.rules if rule.enabled)
    assert len(model_digest(config)) == 64


@pytest.mark.parametrize("content", ["not toml", "rules=[]", "schema_version=9", "[settings"])
def test_bad_configuration_is_sanitized(content: str, tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(content)
    with pytest.raises(PurgeError, match="Invalid or unreadable"):
        load_config(path)
    with pytest.raises(PurgeError):
        load_config(tmp_path / "missing.toml")


def test_query_grouping_and_protections() -> None:
    rule = Rule(name="test", query="from:a@example.com OR category:promotions")
    settings = Settings(
        protected_labels=('Keep "me"', "missing"), excluded_senders=("bank@example.com",)
    )
    query = effective_query(rule, settings, {'Keep "me"'})
    assert query.startswith("(from:a@example.com OR category:promotions)")
    assert '-label:"Keep \\"me\\""' in query
    assert '-from:"bank@example.com"' in query
    assert "missing" not in query
    assert "-in:sent" in query and "-in:drafts" in query
    assert quote_term('a\\b"c') == '"a\\\\b\\"c"'


def test_plan_schema_rejects_duplicate_ids_and_bad_samples() -> None:
    plan = build_plan(FakeMailbox(1), configuration(), clock=lambda: NOW)
    data = plan.payload.model_dump(mode="json")
    item = plan.payload.rules[0]
    duplicated = item.model_copy(update={"message_ids": ("same", "same"), "samples": ()})
    data["rules"] = [duplicated.model_dump(mode="json")]
    with pytest.raises(ValidationError, match="multiple planned actions"):
        PlanPayload.model_validate_json(json.dumps(data))
    wrong_sample = item.model_copy(update={"samples": (Sample(id="not_planned"),)})
    data["rules"] = [wrong_sample.model_dump(mode="json")]
    with pytest.raises(ValidationError, match="Sample IDs"):
        PlanPayload.model_validate_json(json.dumps(data))
    data["rules"] = []
    data["expires_at"] = data["created_at"]
    with pytest.raises(ValidationError, match="expiration"):
        PlanPayload.model_validate_json(json.dumps(data))


def test_plan_rejects_disabled_and_duplicate_names() -> None:
    plan = build_plan(FakeMailbox(0), configuration(), clock=lambda: NOW)
    data = plan.payload.model_dump(mode="json")
    data["rules"] = [item.model_dump(mode="json") for item in plan.payload.rules] * 2
    with pytest.raises(ValidationError, match="unique names"):
        PlanPayload.model_validate_json(json.dumps(data))
    data["rules"] = [
        plan.payload.rules[0]
        .model_copy(update={"rule": Rule(name="disabled", query="x", enabled=False)})
        .model_dump(mode="json")
    ]
    with pytest.raises(ValidationError, match="enabled"):
        PlanPayload.model_validate_json(json.dumps(data))


def test_private_atomic_file_and_no_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "private" / "value.txt"
    write_private_text(path, "first")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    with pytest.raises(SafetyError, match="already exists"):
        write_private_text(path, "second", overwrite=False)
    assert path.read_text() == "first"
    write_private_text(path, "second")
    assert path.read_text() == "second"


def test_atomic_replace_failure_preserves_previous_file(tmp_path: Path) -> None:
    path = tmp_path / "value.txt"
    write_private_text(path, "original")
    with (
        patch("gmail_surgical_purge.storage.os.replace", side_effect=OSError("disk fault")),
        pytest.raises(OSError),
    ):
        write_private_text(path, "new")
    assert path.read_text() == "original"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["value.txt"]


def test_symlinks_and_oversized_artifacts_refused(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(SafetyError):
        write_private_text(link, "bad")
    with pytest.raises(SafetyError):
        read_model(link, Plan)
    with target.open("wb") as handle:
        handle.truncate(MAX_ARTIFACT_BYTES + 1)
    with pytest.raises(SafetyError):
        read_model(target, Plan)


def test_bad_artifact_read_is_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"private":"must not be printed"}')
    with pytest.raises(PurgeError, match="Invalid or unreadable Plan") as error:
        read_model(path, Plan)
    assert "must not be printed" not in str(error.value)
    with pytest.raises(PurgeError):
        read_model(tmp_path / "missing.json", Plan)


def test_lock_rejects_second_process_and_releases(tmp_path: Path) -> None:
    path = tmp_path / "lock"
    with (
        exclusive_lock(path),
        pytest.raises(SafetyError, match="Another process"),
        exclusive_lock(path),
    ):
        pass
    with exclusive_lock(path):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(SafetyError), exclusive_lock(link):
        pass


def test_model_is_frozen() -> None:
    model = Settings()
    with pytest.raises(ValidationError):
        model.batch_size = 10  # type: ignore[misc]


def test_models_written_with_newline(tmp_path: Path) -> None:
    model = configuration()
    path = tmp_path / "config.json"
    write_model(path, model)
    assert path.read_bytes().endswith(b"\n")
    assert read_model(path, RulesConfig) == model
    assert os.path.isfile(path)
