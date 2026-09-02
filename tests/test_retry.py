from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from gmail_surgical_purge.errors import GmailAPIError, PurgeError
from gmail_surgical_purge.retry import RateLimiter, retry_delay


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_statuses(status: int) -> None:
    assert GmailAPIError(status).retryable


@pytest.mark.parametrize("reason", ["rateLimitExceeded", "userRateLimitExceeded"])
def test_rate_limit_403_is_retryable(reason: str) -> None:
    assert GmailAPIError(403, (reason,)).retryable


@pytest.mark.parametrize("status", [301, 400, 401, 403, 404])
def test_permission_and_request_errors_do_not_retry(status: int) -> None:
    assert not GmailAPIError(status, ("domainPolicy",)).retryable


def test_bounded_backoff_and_retry_after() -> None:
    assert retry_delay(0, None, jitter=0) == 1
    assert retry_delay(3, None, jitter=0) == 8
    assert retry_delay(10, None, jitter=0) == 30
    assert retry_delay(1, "10", jitter=0) == 10
    assert retry_delay(1, "nonsense", jitter=0) == 2
    assert retry_delay(1, "NaN", jitter=0) == 2
    assert retry_delay(1, "-5", jitter=0) == 2
    with pytest.raises(PurgeError, match="long pause"):
        retry_delay(1, "120")


def test_http_date_retry_after() -> None:
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=15), usegmt=True)
    assert 12 <= retry_delay(0, future, jitter=0) <= 15


def test_rate_limiter_reserves_slots() -> None:
    delays: list[float] = []
    limiter = RateLimiter(2, clock=lambda: 100, sleep=delays.append)
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()
    assert delays == [0.5, 1.0]
    for rate in (0, -1, 41):
        with pytest.raises(ValueError):
            RateLimiter(rate)
