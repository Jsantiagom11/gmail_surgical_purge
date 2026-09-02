"""Explicit Desktop OAuth bootstrap; unattended commands never open a browser."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from requests import Session

from .errors import PurgeError, SafetyError
from .storage import write_private_text

READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
WRITE_SCOPE = "https://www.googleapis.com/auth/gmail.modify"


def token_path(data_dir: Path, *, write: bool) -> Path:
    return data_dir / ("token-modify.json" if write else "token-readonly.json")


def authorize(credentials_path: Path, data_dir: Path, *, write: bool, browser: bool = True) -> Path:
    if credentials_path.is_symlink():
        raise SafetyError("Refusing a symlink for OAuth client credentials")
    scope = WRITE_SCOPE if write else READ_SCOPE
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scopes=[scope])
        credentials = flow.run_local_server(
            host="127.0.0.1",
            port=0,
            open_browser=browser,
            timeout_seconds=180,
            access_type="offline",
            prompt="consent",
        )
        serialized = cast(str, credentials.to_json())
    except Exception as exc:
        # OAuth errors can contain authorization codes; never echo their payloads.
        raise PurgeError(
            "OAuth authorization failed; verify the Desktop app and test-user settings"
        ) from exc
    destination = token_path(data_dir, write=write)
    write_private_text(destination, serialized + "\n")
    return destination


def session_factory(data_dir: Path, *, write: bool) -> Callable[[], Session]:
    path = token_path(data_dir, write=write)
    if path.is_symlink() or not path.is_file():
        suffix = " --write" if write else ""
        raise SafetyError(f"Missing safe OAuth token. Run gmail-purge auth{suffix} first.")
    scope = WRITE_SCOPE if write else READ_SCOPE

    def create() -> Session:
        try:
            # The official Google package leaves these two constructors untyped.
            credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                str(path), scopes=[scope]
            )
            if not credentials.refresh_token:
                raise ValueError("No refresh token")
            return cast(Session, AuthorizedSession(credentials))  # type: ignore[no-untyped-call]
        except (OSError, ValueError, KeyError) as exc:
            raise PurgeError("Cannot load OAuth token; re-run the matching auth command") from exc

    return create
