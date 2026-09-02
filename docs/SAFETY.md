# Safety model and operational limits

## Before live use

- Review all enabled TOML rules and protect essential records explicitly.
- Export irreplaceable mail independently. This project does not provide a backup.
- Start with a narrowly scoped archive-only pilot; inspect the result in Gmail.
- Review exact counts and representative headers before approving Trash actions.
- Use one data directory and one cleanup process per account.
- Avoid changing mailbox labels or running other cleanup tools during apply.

## What is protected

Every mutation batch checks current message labels. STARRED, IMPORTANT, SENT,
DRAFT, and SPAM are always excluded. Configured user-label identities are also
excluded. Trashed messages are never restored by archive rules. A changed identity
of a protection label between planning and startup stops the operation.

## What is not guaranteed

- Gmail categorization is not a reliable classifier for legal, financial, or sentimental value.
- Optional header samples do not prove that every query match is safe to discard.
- The complete original query is not re-evaluated on apply; its exact reviewed IDs are used.
- Gmail has no atomic compare-and-set for label reads followed by label writes.
  Another client can change a message between those operations.
- Protection-label names/IDs are resolved at apply startup. A new label created
  during the run is not dynamically discovered; avoid concurrent label management.
- A local lock does not coordinate other hosts or processes using another data directory.
- Plans, checkpoints, tokens, and samples are sensitive despite restrictive file modes.
- A checksummed plan is not cryptographically signed or tamper-proof.
- Checkpoints enable resume, not a complete undo operation.
- Trash automatically expires. Do not describe it as durable backup or guaranteed recovery.
- Network, OAuth, quota, disk, and service failures can stop execution. Silent/uninterrupted
  operation cannot be guaranteed; stop conditions are intentional.

## OAuth and distribution

Each user supplies their own Desktop OAuth client and authorizes their own account.
The project does not distribute OAuth secrets or operate a shared OAuth service.
Both readonly and modify Gmail scopes are classified as restricted by Google.
Publishing this source does not establish OAuth verification or compliance for a
hosted multi-user application. [Google scope requirements](https://developers.google.com/workspace/gmail/api/auth/scopes).

Use only the standard Google consent flow. Respect organization policy blocks;
do not work around account or administrator restrictions.

## Recovery

1. Stop the process if the selected mail looks wrong.
2. Inspect the local plan/checkpoint without modifying them.
3. Review affected messages in Gmail Trash or by their destination label.
4. Restore necessary messages before Trash expires; use a separate backup if available.
5. Correct the rules and generate a new plan. Never edit a checksum to force acceptance.

Re-running an unexpired plan uses the same checkpoint. After expiration, inspect
progress and generate a fresh plan against the remaining current state.
