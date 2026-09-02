# Changelog

## 0.1.0 — 2026-09-02

- Replaced an account-specific script with a configurable `src/` package and CLI.
- Added strict TOML/JSON schemas, account binding, checksummed plans, expiration,
  Trash opt-in, protected-message checks, and resumable checkpoints.
- Added separate readonly/modify OAuth setup, bounded concurrent metadata reads,
  serial label batches, sanitized errors, and retry limits.
- Added a synthetic offline demo, network-blocked tests, strict typing, publication
  privacy checks, and a GitHub Actions matrix.
- Removed mailbox-specific data from all public source and documentation.

Initial alpha project. No live Gmail integration test or hosted service is included.
