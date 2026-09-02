from __future__ import annotations

import json
from collections.abc import Sequence
from typing import cast
from unittest.mock import MagicMock

import pytest
from google.auth.exceptions import GoogleAuthError
from requests import ConnectionError, Response, Session

from gmail_surgical_purge.errors import GmailAPIError, PurgeError, SafetyError
from gmail_surgical_purge.gmail import GmailMailbox, error_reasons
from gmail_surgical_purge.models import Settings


def response(status: int, body: object = None, *, retry_after: str | None = None) -> Response:
    result = Response()
    result.status_code = status
    result._content = b"" if body is None else json.dumps(body).encode()
    if retry_after:
        result.headers["Retry-After"] = retry_after
    return result


def client(items: Sequence[Response | BaseException]) -> tuple[GmailMailbox, MagicMock]:
    session = MagicMock(spec=Session)
    session.request.side_effect = items
    mailbox = GmailMailbox(
        Settings(workers=1), lambda: cast(Session, session), sleep=lambda _: None, max_retries=2
    )
    return mailbox, session


def test_profile_labels_and_session_cleanup() -> None:
    mailbox, session = client(
        [
            response(200, {"emailAddress": "owner@example.com"}),
            response(200, {"labels": [{"id": "Label_1", "name": "keep"}]}),
        ]
    )
    with mailbox:
        assert mailbox.account() == "owner@example.com"
        assert mailbox.labels() == {"keep": "Label_1"}
    session.close.assert_called_once()
    assert session.request.call_args.kwargs["allow_redirects"] is False
    assert session.request.call_args.kwargs["timeout"] == (10, 30)


def test_list_pagination_handles_empty_page_and_limits() -> None:
    mailbox, session = client(
        [
            response(200, {"messages": [{"id": "a"}], "nextPageToken": "next"}),
            response(200, {"nextPageToken": "last"}),
            response(200, {"messages": [{"id": "b"}]}),
        ]
    )
    with mailbox:
        assert list(mailbox.iter_ids("in:inbox")) == ["a", "b"]
    calls = session.request.call_args_list
    assert calls[0].kwargs["params"]["maxResults"] == 500
    assert "pageToken" not in calls[0].kwargs["params"]
    assert calls[1].kwargs["params"]["pageToken"] == "next"
    assert calls[2].kwargs["params"]["pageToken"] == "last"


def test_repeated_page_token_stops() -> None:
    mailbox, _ = client([response(200, {"nextPageToken": "same"})] * 2)
    with mailbox, pytest.raises(SafetyError, match="pagination"):
        list(mailbox.iter_ids("x"))


def test_metadata_reads_use_minimal_fields_and_skip_404() -> None:
    mailbox, session = client(
        [response(200, {"id": "a", "labelIds": ["INBOX", "STARRED"]}), response(404)]
    )
    with mailbox:
        snapshots = mailbox.snapshots(("a", "b"))
    assert snapshots["a"] is not None and snapshots["a"].labels == ("INBOX", "STARRED")
    assert snapshots["b"] is None
    assert session.request.call_args_list[0].kwargs["params"]["format"] == "minimal"
    assert session.request.call_args_list[0].kwargs["params"]["fields"] == "id,labelIds"


def test_metadata_permissions_are_not_ignored() -> None:
    mailbox, _ = client([response(403)])
    with mailbox, pytest.raises(GmailAPIError):
        mailbox.snapshots(("a",))


def test_samples_are_header_only() -> None:
    mailbox, session = client(
        [
            response(
                200,
                {
                    "id": "a",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "sender@example.com"},
                            {"name": "SUBJECT", "value": "Synthetic"},
                            {"name": "Date", "value": "Thu, 1 Jan 2026"},
                        ]
                    },
                },
            )
        ]
    )
    with mailbox:
        samples = mailbox.samples(("a",))
    assert samples[0].sender == "sender@example.com"
    assert samples[0].subject == "Synthetic"
    assert samples[0].date == "Thu, 1 Jan 2026"
    assert session.request.call_args.kwargs["params"]["format"] == "metadata"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_responses_retry(status: int) -> None:
    mailbox, session = client(
        [response(status), response(200, {"emailAddress": "owner@example.com"})]
    )
    with mailbox:
        assert mailbox.account() == "owner@example.com"
    assert session.request.call_count == 2


def test_only_rate_limit_403_retries() -> None:
    transient = response(403, {"error": {"errors": [{"reason": "userRateLimitExceeded"}]}})
    mailbox, session = client([transient, response(200, {"emailAddress": "owner@example.com"})])
    with mailbox:
        mailbox.account()
    assert session.request.call_count == 2
    blocked = response(403, {"error": {"errors": [{"reason": "domainPolicy"}]}})
    mailbox, session = client([blocked])
    with mailbox, pytest.raises(GmailAPIError, match="domainPolicy"):
        mailbox.account()
    assert session.request.call_count == 1


def test_retry_exhaustion_and_transport_errors_are_sanitized() -> None:
    mailbox, session = client([ConnectionError("private-url-and-token")] * 3)
    with mailbox, pytest.raises(PurgeError, match="transport") as error:
        mailbox.account()
    assert "private-url" not in str(error.value)
    assert session.request.call_count == 3
    mailbox, session = client([response(503)] * 3)
    with mailbox, pytest.raises(GmailAPIError):
        mailbox.account()
    assert session.request.call_count == 3


def test_transport_can_recover() -> None:
    mailbox, session = client(
        [ConnectionError(), response(200, {"emailAddress": "owner@example.com"})]
    )
    with mailbox:
        assert mailbox.account() == "owner@example.com"
    assert session.request.call_count == 2


def test_auth_failure_never_retried_as_rate_limit() -> None:
    error = GoogleAuthError("private")  # type: ignore[no-untyped-call]
    mailbox, session = client([error])
    with mailbox, pytest.raises(PurgeError, match="OAuth refresh"):
        mailbox.account()
    assert session.request.call_count == 1


def test_long_retry_after_stops_for_manual_resume() -> None:
    mailbox, session = client([response(429, retry_after="120")])
    with mailbox, pytest.raises(PurgeError, match="long pause"):
        mailbox.account()
    assert session.request.call_count == 1


def test_modify_is_bounded_and_has_no_delete_endpoint() -> None:
    mailbox, session = client([response(204)])
    with mailbox:
        mailbox.modify(("a", "b"), ("TRASH",), ("INBOX",))
        for ids in ((), tuple(str(i) for i in range(1001))):
            with pytest.raises(SafetyError):
                mailbox.modify(ids, ("TRASH",), ("INBOX",))
        with pytest.raises(SafetyError, match="INBOX"):
            mailbox.modify(("a",), (), ("STARRED",))
    assert session.request.call_count == 1
    call = session.request.call_args
    assert call.args[0] == "POST" and call.args[1].endswith("/messages/batchModify")
    assert call.kwargs["json"] == {
        "ids": ["a", "b"],
        "addLabelIds": ["TRASH"],
        "removeLabelIds": ["INBOX"],
    }
    assert not hasattr(mailbox, "delete")


def test_label_creation_and_existing_conflict() -> None:
    mailbox, session = client([response(200, {"id": "Label_1", "name": "99_ARCHIVE"})])
    with mailbox:
        assert mailbox.create_label("99_ARCHIVE") == "Label_1"
    assert session.request.call_args.kwargs["json"]["labelListVisibility"] == "labelHide"
    mailbox, _ = client(
        [response(409), response(200, {"labels": [{"id": "Label_2", "name": "keep"}]})]
    )
    with mailbox:
        assert mailbox.create_label("keep") == "Label_2"


def test_label_creation_unknown_outcome_never_blindly_retried() -> None:
    mailbox, session = client([ConnectionError("lost ack")])
    with mailbox, pytest.raises(PurgeError):
        mailbox.create_label("keep")
    assert session.request.call_count == 1
    mailbox, _ = client([response(409), response(200, {"labels": []})])
    with mailbox, pytest.raises(GmailAPIError):
        mailbox.create_label("missing")


def test_error_payload_is_sanitized() -> None:
    assert error_reasons("not-json") == ()
    assert error_reasons('{"error":{"errors":[{"reason":"invalid private text"}]}}') == ()
    assert error_reasons('{"error":{"errors":[{"reason":"domainPolicy"}]}}') == ("domainPolicy",)
