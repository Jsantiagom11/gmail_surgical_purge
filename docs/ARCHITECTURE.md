# Architecture and decisions

## Scope

One local user, one Gmail account, one reviewed cleanup operation. The system
archives or moves messages to Trash. It does not send mail, unsubscribe through
email links, hard-delete messages, download bodies/attachments, or create Gmail filters.

## State transitions

1. TOML configuration is parsed with strict, versioned Pydantic models.
2. Read-only queries are fully paginated before mutation. First match wins.
3. A checksummed plan stores exact IDs, settings, account, expiration, and optional header samples.
4. Human review supplies the plan token and, separately, approval for Trash actions.
5. Apply validates the plan/checkpoint, account, and protected label identities.
6. Each batch reads current message labels, excludes protected/missing IDs, and modifies eligible IDs.
7. A private atomic checkpoint records progress. Restart repeats an uncertain batch safely.

Planning never creates labels or changes Gmail. Labels are created during apply
only when there are eligible messages that need them.

## Why these choices

| Decision | Benefit | Cost/limitation |
|---|---|---|
| Exact IDs rather than repeating a mutable search | The reviewed target does not silently expand as new mail arrives. | O(N) plan storage and memory; query conditions are not fully re-evaluated during apply. |
| Message-level mutations | Avoids applying a thread action to unrelated messages in the same conversation. | Requires careful per-message accounting. |
| Metadata before every batch | Catches stars, Important, Sent/Draft/Spam, and known protected labels added since planning. | One additional GET per candidate, plus rate-limited latency. |
| Serial writes, bounded parallel reads | Controls concurrency and quota pressure while reusing connections. | Not the fastest possible bulk-deletion implementation. |
| Separate readonly/modify OAuth tokens | Planning does not need write authorization. | Two explicit consent flows. |
| Atomic JSON checkpoint | Inspectable, small, and straightforward to recover. | One local process per data directory; not a distributed lock. |
| No hard-delete endpoint | Prevents this client from bypassing Trash recovery. | Trash can still auto-expire; not a backup. |
| Conservative error handling | Permission/config errors stop instead of being silently skipped. | Some mailbox races require a manual rerun. |

## Retry semantics

- Retry: HTTP 429, 5xx, transient transport errors, and the specific 403 rate-limit reasons.
- Stop: other 4xx, authorization/policy failures, long Retry-After windows, or exhausted retries.
- Batch label mutations are idempotent. A lost acknowledgement can be replayed.
- Label creation is not blindly retried after an unknown outcome. A later run re-lists labels.
- A 404 does not automatically mean every message disappeared. Fresh metadata must confirm it.

Counters distinguish acknowledged writes (`applied`), already-satisfied targets
(`already_done`), protected messages, and confirmed missing messages. A crash after
a successful write can shift accounting from `applied` to `already_done` on replay.

## Boundaries

`Mailbox` is a typed protocol. Domain code does not depend on Google's dynamic
response objects. The REST adapter validates wire data and never prints raw error
bodies. Two narrow mypy suppressions document untyped constructors in the official
Google authentication library; strict checks remain enabled for project code.

## References

- [Gmail list pagination](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)
- [Gmail batchModify limit](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/batchModify)
- [Gmail error handling](https://developers.google.com/workspace/gmail/api/guides/handle-errors)
- [Google OAuth scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
