"""Gmail REST adapter: bounded parallel reads, serial idempotent writes, no delete API."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from types import TracebackType
from typing import Self

from google.auth.exceptions import GoogleAuthError
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from requests import RequestException, Session

from .errors import GmailAPIError, PurgeError, SafetyError
from .models import Sample, Settings, Snapshot, Source
from .retry import RateLimiter, retry_delay

BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_PAGE = 500
MAX_BATCH = 1000
Params = dict[str, str | int | list[str]]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class MessageRef(WireModel):
    id: str


class Page(WireModel):
    messages: tuple[MessageRef, ...] = ()
    nextPageToken: str | None = None


class Label(WireModel):
    id: str
    name: str


class LabelList(WireModel):
    labels: tuple[Label, ...] = ()


class Profile(WireModel):
    emailAddress: str


class MessageLabels(WireModel):
    id: str
    labelIds: tuple[str, ...] = ()


class Header(WireModel):
    name: str
    value: str


class Payload(WireModel):
    headers: tuple[Header, ...] = ()


class Metadata(WireModel):
    id: str
    payload: Payload = Field(default_factory=Payload)


class Reason(WireModel):
    reason: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")


class ErrorDetail(WireModel):
    errors: tuple[Reason, ...] = ()


class ErrorEnvelope(WireModel):
    error: ErrorDetail = Field(default_factory=ErrorDetail)


def error_reasons(body: str) -> tuple[str, ...]:
    try:
        error = ErrorEnvelope.model_validate_json(body)
        return tuple(sorted({item.reason for item in error.error.errors}))
    except ValidationError:
        return ()


class GmailMailbox:
    source: Source = "gmail"

    def __init__(
        self,
        settings: Settings,
        session_factory: Callable[[], Session],
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 6,
    ) -> None:
        self._factory = session_factory
        self._sleep = sleep
        self._max_retries = max_retries
        self._limiter = RateLimiter(settings.requests_per_second, sleep=sleep)
        self._local = threading.local()
        self._sessions: list[Session] = []
        self._sessions_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=settings.workers, thread_name_prefix="gmail-read"
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
        for session in self._sessions:
            session.close()

    def _session(self) -> Session:
        session: object = getattr(self._local, "session", None)
        if not isinstance(session, Session):
            session = self._factory()
            self._local.session = session
            with self._sessions_lock:
                self._sessions.append(session)
        return session

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Params | None = None,
        body: dict[str, object] | None = None,
        idempotent: bool = True,
    ) -> str:
        for attempt in range(self._max_retries + 1):
            self._limiter.acquire()
            try:
                response = self._session().request(
                    method,
                    f"{BASE_URL}{path}",
                    params=params,
                    json=body,
                    timeout=(10, 30),
                    allow_redirects=False,
                )
            except GoogleAuthError as exc:
                raise PurgeError("OAuth refresh failed. Re-authorize before resuming.") from exc
            except RequestException as exc:
                if not idempotent or attempt == self._max_retries:
                    raise PurgeError(
                        "Gmail transport failed; the checkpoint remains resumable"
                    ) from exc
                self._sleep(retry_delay(attempt, None))
                continue
            if 200 <= response.status_code < 300:
                return response.text
            error = GmailAPIError(response.status_code, error_reasons(response.text))
            if not idempotent or not error.retryable or attempt == self._max_retries:
                raise error
            self._sleep(retry_delay(attempt, response.headers.get("Retry-After")))
        raise AssertionError("unreachable")

    def account(self) -> str:
        body = self._request("GET", "/profile", params={"fields": "emailAddress"})
        return Profile.model_validate_json(body).emailAddress

    def labels(self) -> dict[str, str]:
        body = self._request("GET", "/labels", params={"fields": "labels(id,name)"})
        return {label.name: label.id for label in LabelList.model_validate_json(body).labels}

    def iter_ids(self, query: str) -> Iterator[str]:
        next_token: str | None = None
        visited_tokens: set[str] = set()
        while True:
            params: Params = {
                "q": query,
                "maxResults": MAX_PAGE,
                "includeSpamTrash": "false",
                "fields": "messages/id,nextPageToken",
            }
            if next_token:
                params["pageToken"] = next_token
            page = Page.model_validate_json(self._request("GET", "/messages", params=params))
            for message in page.messages:
                yield message.id
            next_token = page.nextPageToken
            if not next_token:
                return
            if next_token in visited_tokens:
                raise SafetyError("Gmail repeated a pagination token; no plan was accepted")
            visited_tokens.add(next_token)

    def _snapshot(self, message_id: str) -> Snapshot | None:
        try:
            body = self._request(
                "GET",
                f"/messages/{message_id}",
                params={"format": "minimal", "fields": "id,labelIds"},
            )
        except GmailAPIError as exc:
            if exc.status == 404:
                return None
            raise
        result = MessageLabels.model_validate_json(body)
        return Snapshot(id=result.id, labels=result.labelIds)

    def snapshots(self, message_ids: Sequence[str]) -> dict[str, Snapshot | None]:
        results = self._executor.map(self._snapshot, message_ids)
        return dict(zip(message_ids, results, strict=True))

    def samples(self, message_ids: Sequence[str]) -> tuple[Sample, ...]:
        samples: list[Sample] = []
        for message_id in message_ids:
            body = self._request(
                "GET",
                f"/messages/{message_id}",
                params={
                    "format": "metadata",
                    "metadataHeaders": ["From", "Subject", "Date"],
                    "fields": "id,payload/headers",
                },
            )
            message = Metadata.model_validate_json(body)
            headers = {header.name.casefold(): header.value for header in message.payload.headers}
            samples.append(
                Sample(
                    id=message.id,
                    sender=headers.get("from", ""),
                    subject=headers.get("subject", ""),
                    date=headers.get("date", ""),
                )
            )
        return tuple(samples)

    def create_label(self, name: str) -> str:
        try:
            body = self._request(
                "POST",
                "/labels",
                body={
                    "name": name,
                    "labelListVisibility": "labelHide"
                    if name == "99_ARCHIVE"
                    else "labelShowIfUnread",
                    "messageListVisibility": "show",
                },
                idempotent=False,
            )
        except GmailAPIError as exc:
            if exc.status == 409:
                existing = self.labels().get(name)
                if existing:
                    return existing
            raise
        return Label.model_validate_json(body).id

    def modify(
        self,
        message_ids: Sequence[str],
        add_labels: Sequence[str],
        remove_labels: Sequence[str],
    ) -> None:
        if not 1 <= len(message_ids) <= MAX_BATCH:
            raise SafetyError("Mutation batches must contain 1..1000 message IDs")
        if tuple(remove_labels) != ("INBOX",):
            raise SafetyError("The adapter only permits removing INBOX")
        self._request(
            "POST",
            "/messages/batchModify",
            body={
                "ids": list(message_ids),
                "addLabelIds": list(add_labels),
                "removeLabelIds": list(remove_labels),
            },
        )
