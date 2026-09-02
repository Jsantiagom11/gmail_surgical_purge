from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from requests import Session

from gmail_surgical_purge.auth import (
    READ_SCOPE,
    WRITE_SCOPE,
    authorize,
    session_factory,
    token_path,
)
from gmail_surgical_purge.errors import PurgeError, SafetyError


def test_scope_separation() -> None:
    directory = Path("private")
    assert token_path(directory, write=False) != token_path(directory, write=True)
    assert READ_SCOPE.endswith("readonly") and WRITE_SCOPE.endswith("modify")


@pytest.mark.parametrize("write", [False, True])
def test_explicit_oauth_bootstrap(write: bool, tmp_path: Path) -> None:
    credentials = tmp_path / "client.json"
    credentials.write_text("{}")
    flow = MagicMock()
    flow.run_local_server.return_value.to_json.return_value = '{"synthetic": true}'
    with patch(
        "gmail_surgical_purge.auth.InstalledAppFlow.from_client_secrets_file", return_value=flow
    ) as factory:
        result = authorize(credentials, tmp_path, write=write, browser=False)
    assert result == token_path(tmp_path, write=write)
    assert result.read_text().endswith("\n")
    assert factory.call_args.kwargs["scopes"] == [WRITE_SCOPE if write else READ_SCOPE]
    assert flow.run_local_server.call_args.kwargs["open_browser"] is False


def test_oauth_errors_and_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "client.json"
    target.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(SafetyError):
        authorize(link, tmp_path, write=False)
    with (
        patch(
            "gmail_surgical_purge.auth.InstalledAppFlow.from_client_secrets_file",
            side_effect=ValueError("secret"),
        ),
        pytest.raises(PurgeError) as error,
    ):
        authorize(target, tmp_path, write=False)
    assert "secret" not in str(error.value)


def test_no_implicit_interactive_auth(tmp_path: Path) -> None:
    with pytest.raises(SafetyError, match="auth --write"):
        session_factory(tmp_path, write=True)
    with pytest.raises(SafetyError, match="auth"):
        session_factory(tmp_path, write=False)


def test_worker_session_factory(tmp_path: Path) -> None:
    path = token_path(tmp_path, write=False)
    path.write_text("{}")
    credentials = MagicMock()
    credentials.refresh_token = "synthetic"
    session = MagicMock(spec=Session)
    with (
        patch(
            "gmail_surgical_purge.auth.Credentials.from_authorized_user_file",
            return_value=credentials,
        ),
        patch("gmail_surgical_purge.auth.AuthorizedSession", return_value=session),
    ):
        factory = session_factory(tmp_path, write=False)
        assert factory() is cast(Session, session)
        credentials.refresh_token = None
        with pytest.raises(PurgeError, match="load OAuth token"):
            factory()


def test_session_factory_invalid_file(tmp_path: Path) -> None:
    token_path(tmp_path, write=True).write_text("not JSON")
    factory = session_factory(tmp_path, write=True)
    with pytest.raises(PurgeError):
        factory()
