# Verification evidence

Verification date: **2026-09-02 (UTC)**. Version: **0.1.0 alpha**.

This is a local verification record, not a security certification, live-mailbox
benchmark, GitHub Actions result, or proof of publication.

## Measured local checks

| Gate | Result |
|---|---|
| Interpreter | Python 3.12.13, Linux |
| Environment | uv 0.11.33; frozen `uv.lock`, public PyPI sources |
| Formatting | Ruff format check passed |
| Lint | Ruff check passed |
| Types | mypy strict passed for 24 source/test/script files |
| Tests | 116 passed with network sockets disabled |
| Coverage | 99.42%, including branch coverage; required minimum 85% |
| Distributions | Source archive and wheel built successfully |
| Distribution metadata | Both distributions passed `twine check` |
| Wheel smoke test | Isolated wheel installation printed `gmail-purge 0.1.0` |
| Public-source guard | Passed for 47 staged files; no likely private payloads detected |

The metadata format is explicitly set to Core Metadata 2.4 for wheel and source
archives. This resolved an observed validator incompatibility with automatically
generated 2.5 metadata; the validation gate was not disabled.

The publication scanner rejects oversized input before pattern matching and
bounds its email pattern. Its oversized-input regression case is part of the suite.

## Synthetic 12,000-message scenario

```json
{
  "mode": "SYNTHETIC_OFFLINE_DEMO",
  "network_requests": 0,
  "planned": 12000,
  "applied": 11880,
  "protected": 120,
  "mutation_batches": 12,
  "largest_batch": 990,
  "completed": true
}
```

This scenario adds protections after planning, then proves that apply skips those
messages. It also exercises more than 10,000 candidates, bounded mutation size,
checkpoint persistence, and completion. It does not measure Gmail quota behavior
or real-world elapsed time.

## Reproduce

Run from a Git checkout, after staging only reviewed public source:

```bash
bash scripts/check.sh
uv run --isolated --no-project --with dist/*.whl gmail-purge --version
uv run --frozen gmail-purge demo --messages 12000 --output .gmail-purge/evidence-demo
git diff --check
git diff --cached --check
```

The demo refuses to overwrite an existing output directory. Choose another path
for a subsequent run. Raw demo plans/checkpoints are intentionally not versioned.

## Not verified here

- Live Gmail OAuth, reads, writes, latency, or behavior on any real mailbox.
- Python 3.11 and 3.13 execution; they are configured in remote CI but not run locally.
- A successful remote GitHub Actions run or public/private repository creation.
- Absence of every possible secret or personal datum; the scanner is heuristic.
- Legal retention requirements, OAuth app verification, or production readiness.
- Byte-identical builds across operating systems or future build-backend releases.

For authority boundaries and remaining risks, see [SAFETY.md](SAFETY.md).
