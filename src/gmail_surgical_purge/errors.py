"""User-facing exceptions that do not expose mail or OAuth payloads."""


class PurgeError(Exception):
    """An operational failure safe to display on stderr."""


class SafetyError(PurgeError):
    """A guard rejected the operation before further mutation."""


class GmailAPIError(PurgeError):
    """Sanitized HTTP error; response bodies and URLs are deliberately excluded."""

    def __init__(self, status: int, reasons: tuple[str, ...] = ()) -> None:
        self.status = status
        self.reasons = reasons
        suffix = ", ".join(reasons) if reasons else "request rejected"
        super().__init__(f"Gmail API HTTP {status}: {suffix}")

    @property
    def retryable(self) -> bool:
        rate_reasons = {"rateLimitExceeded", "userRateLimitExceeded"}
        return (
            self.status == 429
            or 500 <= self.status <= 599
            or (self.status == 403 and bool(rate_reasons.intersection(self.reasons)))
        )
