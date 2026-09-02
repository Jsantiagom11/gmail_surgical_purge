# Security

## Sensitive material

Never attach OAuth client files, refresh/access tokens, plans, checkpoints, real
message IDs, headers, mailbox exports, or application logs to a public issue.
The local publication check is a heuristic, not a complete secret scanner.

## Reporting

If GitHub private vulnerability reporting is enabled for the repository, use its
Security tab. Otherwise, open a minimal issue requesting a private contact channel,
without exploit details or sensitive data. No private reporting channel is implied
until it has actually been configured by the repository owner.

## Exposure response

1. Revoke affected Google account access and replace compromised OAuth credentials.
2. Stop scheduled or running processes that use the affected material.
3. Inspect repository history and distribution archives; removing a current file
   alone does not remove earlier copies.
4. Document the incident without republishing the secret.

This alpha release has no independent security audit. See [the safety model](docs/SAFETY.md).
