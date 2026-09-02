from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gmail_surgical_purge.cli import build_parser, main, plan_summary, state_path_for
from gmail_surgical_purge.demo import DemoMailbox, run_demo
from gmail_surgical_purge.engine import build_plan
from gmail_surgical_purge.errors import PurgeError, SafetyError
from gmail_surgical_purge.models import Plan, Rule
from gmail_surgical_purge.storage import read_model, write_model

from .helpers import FakeMailbox, configuration


def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "rules.toml"
    path.write_text('[[rules]]\nname="archive"\nquery="in:inbox"\naction="archive"\n')
    return path


def fake_context(box: FakeMailbox) -> MagicMock:
    manager = MagicMock()
    manager.__enter__.return_value = box
    return manager


def test_help_version_and_module_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    for args in (["--help"], ["--version"]):
        with pytest.raises(SystemExit) as error:
            main(args)
        assert error.value.code == 0
    monkeypatch.setattr(sys, "argv", ["gmail-purge", "--version"])
    with pytest.raises(SystemExit) as error:
        runpy.run_module("gmail_surgical_purge", run_name="__main__")
    assert error.value.code == 0
    assert build_parser().parse_args(["demo"]).messages == 12000


def test_config_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["config-check", "--config", str(config_file(tmp_path))]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_demo_review_status_and_live_apply_rejection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "runtime"
    assert main(["demo", "--messages", "120", "--data-dir", str(directory)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["network_requests"] == 0 and summary["applied"] == 118
    path = directory / "demo" / "plan.json"
    assert main(["review", "--plan", str(path), "--show-samples"]) == 0
    review = json.loads(capsys.readouterr().out)
    assert review["source"] == "demo" and review["rules"][0]["samples"]
    assert main(["status", "--plan", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["completed"] is True
    assert main(["apply", "--plan", str(path), "--confirm", review["confirmation_token"]]) == 2
    assert "Synthetic" in capsys.readouterr().err


def test_invalid_demo_and_output_reuse(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_demo(tmp_path / "bad", 0)
    run_demo(tmp_path / "demo", 1)
    with pytest.raises(SafetyError):
        run_demo(tmp_path / "demo", 1)


def test_demo_mailbox_existing_label() -> None:
    mailbox = DemoMailbox(0)
    assert mailbox.account() == "demo@example.com"
    first = mailbox.create_label("archive")
    assert mailbox.create_label("archive") == first
    assert mailbox.labels()["archive"] == first


def test_status_before_apply(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plan = build_plan(FakeMailbox(1), configuration())
    path = tmp_path / "plan.json"
    write_model(path, plan)
    assert main(["status", "--plan", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == {"started": False, "total": 1}
    assert state_path_for(path, tmp_path / "override.json") == tmp_path / "override.json"


def test_plan_and_apply_via_cli_with_fake_gmail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    box = FakeMailbox(12)
    config = config_file(tmp_path)
    directory = tmp_path / "runtime"
    path = directory / "plan.json"
    with (
        patch("gmail_surgical_purge.cli.session_factory"),
        patch("gmail_surgical_purge.cli.GmailMailbox", return_value=fake_context(box)),
    ):
        assert main(["plan", "--config", str(config), "--data-dir", str(directory)]) == 0
        planned = json.loads(capsys.readouterr().out)
        assert planned["total"] == 12 and not box.calls
        assert main(["plan", "--config", str(config), "--data-dir", str(directory)]) == 2
        assert "already exists" in capsys.readouterr().err
        assert (
            main(
                [
                    "apply",
                    "--plan",
                    str(path),
                    "--data-dir",
                    str(directory),
                    "--confirm",
                    planned["confirmation_token"],
                ]
            )
            == 0
        )
        result = capsys.readouterr()
        assert json.loads(result.out)["applied"] == 12
        assert "visited=12" in result.err
        assert (
            main(
                [
                    "apply",
                    "--plan",
                    str(path),
                    "--data-dir",
                    str(directory),
                    "--confirm",
                    planned["confirmation_token"],
                    "--quiet",
                ]
            )
            == 0
        )
        assert capsys.readouterr().err == ""
    assert read_model(path, Plan).payload.source == "gmail"


def test_audit_and_auth_are_explicitly_mocked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    box = FakeMailbox()
    with (
        patch("gmail_surgical_purge.cli.session_factory"),
        patch("gmail_surgical_purge.cli.GmailMailbox", return_value=fake_context(box)),
    ):
        assert main(["audit", "--data-dir", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["account"] == "owner@example.com"
    with patch("gmail_surgical_purge.cli.authorize", return_value=tmp_path / "token.json") as auth:
        assert (
            main(
                [
                    "auth",
                    "--credentials",
                    str(tmp_path / "client.json"),
                    "--data-dir",
                    str(tmp_path),
                    "--write",
                    "--no-browser",
                ]
            )
            == 0
        )
    assert auth.call_args.kwargs == {"write": True, "browser": False}
    assert json.loads(capsys.readouterr().out)["authorized"] == "modify"


@pytest.mark.parametrize(
    ("error", "code", "expected"),
    [
        (SafetyError("guard"), 2, "Safety stop"),
        (ValueError("private"), 2, "validation"),
        (PurgeError("operational"), 3, "Operational stop"),
        (OSError("private"), 3, "Local I/O"),
        (KeyboardInterrupt(), 130, "Interrupted"),
    ],
)
def test_exit_codes_are_sanitized(
    error: BaseException, code: int, expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch("gmail_surgical_purge.cli.run", side_effect=error):
        assert main(["demo"]) == code
    result = capsys.readouterr()
    assert expected in result.err and "private" not in result.err


def test_review_summary_excludes_samples_unless_requested() -> None:
    plan = build_plan(FakeMailbox(2), configuration(Rule(name="archive", query="x")))
    summary = plan_summary(plan)
    assert "samples" not in json.dumps(summary)
    assert "samples" in json.dumps(plan_summary(plan, samples=True))
