"""TOML loading and safe composition of Gmail search queries."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from pydantic import ValidationError

from .errors import PurgeError
from .models import Rule, RulesConfig, Settings


def load_config(path: Path) -> RulesConfig:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        return RulesConfig.model_validate_json(json.dumps(data))
    except (OSError, tomllib.TOMLDecodeError, ValidationError, TypeError) as exc:
        raise PurgeError(
            "Invalid or unreadable rules TOML; run config-check for schema guidance"
        ) from exc


def quote_term(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def effective_query(rule: Rule, settings: Settings, present_labels: set[str]) -> str:
    guards = ["-in:trash", "-in:spam", "-in:sent", "-in:drafts", "-is:starred", "-is:important"]
    guards.extend(
        f"-label:{quote_term(label)}"
        for label in settings.protected_labels
        if label in present_labels
    )
    guards.extend(f"-from:{quote_term(sender)}" for sender in settings.excluded_senders)
    return " ".join([f"({rule.query})", *guards])
