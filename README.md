# Gmail Surgical Purge

Plan-first Gmail cleanup with reviewed message IDs, explicit approval, bounded API
batches, and resumable execution. Built for Python 3.11+ on Linux and WSL2.

**Status: v0.1.0 alpha.** This is a local CLI, not a hosted email service. It does
not promise error-free classification, permanent recovery, or uninterrupted service.
No real mailbox data, credentials, or customer-specific rules are included.

## Try the offline demo

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from
the repository root:

```bash
uv sync --locked --dev
uv run --frozen gmail-purge demo --messages 12000
```

The demo uses synthetic data only. Expected result:

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

Demo output is private local runtime material under `.gmail-purge/demo/`. To run
again, provide a new `--output` directory. A synthetic plan cannot be applied to Gmail.
These numbers demonstrate control flow, **not live Gmail throughput**.

## Safety model

| Control | Behavior |
|---|---|
| Safe initial configuration | Archive-only enabled rules; the example Trash rule is disabled. |
| Read-only planning | Collects exact message IDs before any mailbox mutation. |
| Review gate | SHA-256 checksum plus a plan-specific confirmation token. |
| Trash gate | Also requires `--allow-trash`; no permanent-delete endpoint exists. |
| Account binding | The authenticated account must match the reviewed plan. |
| Freshness | Plans expire after 24 hours by default. |
| Message protections | Stars, Important, Sent, Drafts, Spam, and configured protected labels are checked again immediately before each batch. |
| Thread safety | Operates on message IDs, not whole conversation threads. |
| Resume | Atomic checkpoints, bounded retries, and idempotent label mutations. |
| Private artifacts | Local files are created with mode `0600`; runtime paths are ignored by Git. |

A checksum detects accidental changes; it is **not a signature** and does not
protect against a malicious local user who can rewrite both a plan and its hash.
Gmail does not offer an atomic compare-and-set between metadata reads and label
updates. Avoid concurrent mailbox cleanup, and read [the safety limits](docs/SAFETY.md).

## Live workflow

### 1. Configure locally

```bash
cp config/rules.example.toml config.local.toml
uv run --frozen gmail-purge config-check --config config.local.toml
```

Edit `config.local.toml` with your own protected labels and sender exclusions.
Rules are ordered: the first matching rule owns each message. Never publish this
file once it contains personal information.

### 2. Authorize read-only access

Create your own Google Cloud project, enable Gmail API, and configure a Desktop
OAuth client using the [official Python setup guide](https://developers.google.com/workspace/gmail/api/quickstart/python).
Keep the downloaded client configuration under `.gmail-purge/`.

```bash
uv run --frozen gmail-purge auth --credentials .gmail-purge/client.json
uv run --frozen gmail-purge audit
```

Use `--no-browser` when you need to open the displayed loopback authorization URL
manually. OAuth bootstrap is interactive; ordinary planning and execution never
launch a login flow automatically.

### 3. Plan, then review

```bash
uv run --frozen gmail-purge plan \
  --config config.local.toml \
  --output .gmail-purge/pilot-plan.json \
  --max-messages 2000

uv run --frozen gmail-purge review \
  --plan .gmail-purge/pilot-plan.json \
  --show-samples
```

The cap is a hard refusal threshold, not silent truncation. Narrow a rule by date
or sender if it matches too much. After a successful small pilot, explicitly raise
`--max-messages` for a larger plan, up to 1,000,000.

Review the account, queries, actions, counts, and samples. A sample is not proof
that every matching message is disposable. Protect essential records first and
export irreplaceable mail before using Trash.

### 4. Authorize writes and apply the reviewed plan

```bash
uv run --frozen gmail-purge auth \
  --credentials .gmail-purge/client.json --write

uv run --frozen gmail-purge apply \
  --plan .gmail-purge/pilot-plan.json \
  --confirm APPLY-REPLACE_WITH_REVIEW_TOKEN
```

For a plan containing Trash actions, add `--allow-trash` after reviewing it. The
program moves those messages to Gmail Trash; Gmail normally removes Trash after
30 days. This is not a backup. [Google: delete or recover messages](https://support.google.com/mail/answer/7401).

### 5. Resume or inspect

```bash
uv run --frozen gmail-purge status --plan .gmail-purge/pilot-plan.json

# Resume by repeating the exact same apply command and token.
uv run --frozen gmail-purge apply \
  --plan .gmail-purge/pilot-plan.json \
  --confirm APPLY-REPLACE_WITH_REVIEW_TOKEN --quiet
```

`--quiet` suppresses progress lines, not safety failures or the final JSON result.
Do not delete the checkpoint to force replay. If the plan expires, review progress
and create a new plan against the remaining mailbox state.

## Architecture

| Module | Responsibility |
|---|---|
| `models.py`, `config.py` | Strict schemas, rule configuration, search exclusions, checksums. |
| `engine.py`, `ports.py` | Pure orchestration, approval gates, deduplication, protection checks, resume. |
| `gmail.py`, `auth.py`, `retry.py` | Gmail REST boundary, separate OAuth scopes, per-thread sessions, rate limiting. |
| `storage.py` | Private atomic writes, no-clobber plan creation, POSIX process lock. |
| `cli.py`, `demo.py` | User-facing commands and a credential-free synthetic demo. |

Writes are serial and capped at 1,000 message IDs. Metadata reads use a bounded
`ThreadPoolExecutor` with one authenticated session per worker and a shared rate
limit. The default is four workers, 20 requests/second, and 250 IDs per mutation.

The extra metadata reads are deliberate: throughput is not prioritized over
checking current protections. A large plan uses O(N) memory for its exact ID list.
See [architecture decisions](docs/ARCHITECTURE.md).

## Development and verification

```bash
uv sync --locked --dev
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy
uv run --frozen pytest
uv build
uv run --frozen twine check dist/*
```

All tests block network sockets. They exercise fake Gmail responses, interruptions,
stale IDs, protected mail, OAuth boundaries, and batches above 10,000 synthetic
messages. There is no live-mailbox integration test or claim of production certification.

GitHub Actions is configured for Python 3.11, 3.12, and 3.13 with read-only repository
permissions, pinned action commits, and no Gmail secrets. Remote CI results must be
checked after the repository is actually pushed.

## Documentation

- [Guía operativa en español](docs/RUNBOOK_ES.md)
- [Safety model and limitations](docs/SAFETY.md)
- [Architecture and tradeoffs](docs/ARCHITECTURE.md)
- [Verification evidence](docs/EVIDENCE.md)
- [Estado recuperable y siguientes pasos](CURRENT_STATE.md)
- [Publishing this project](docs/PUBLISHING.md)
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md), [changelog](CHANGELOG.md)

## License status

No open-source license has been selected. See [LICENSE_NOTICE.md](LICENSE_NOTICE.md).
Publishing source on GitHub is separate from choosing a reuse license.

Independent project; not affiliated with or endorsed by Google.
