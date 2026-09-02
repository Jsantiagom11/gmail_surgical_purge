# Contributing

## Local environment

```bash
uv sync --locked --dev
uv run --frozen ruff format .
uv run --frozen ruff check .
uv run --frozen mypy
uv run --frozen pytest
```

After staging reviewed source changes, `bash scripts/check.sh` also validates the
Git index for private payloads and builds/checks distributions.

## Definition of done

- Strict schemas and typing remain enabled; do not hide new errors with broad ignores.
- Tests pass with network sockets disabled and coverage at or above the configured minimum.
- No tokens, credentials, message IDs, real headers, mailbox statistics, or personal rules are staged.
- Matching, safety, recovery, and quota behavior are documented when changed.
- A release is not described as live-tested unless a separate authorized integration test is recorded.
- Do not add permanent deletion, implicit OAuth, or automatic approval as incidental refactoring.

Use synthetic fixtures and reserved example domains. Keep pull requests small and
include failure-path tests. Public issue reports must contain no private mailbox data.
