# Publication and maintenance

The project is published at
[Jsantiagom11/gmail_surgical_purge](https://github.com/Jsantiagom11/gmail_surgical_purge).
Do not create a second repository to continue this project.

## Work from the current source

```bash
git clone https://github.com/Jsantiagom11/gmail_surgical_purge.git
cd gmail_surgical_purge
uv sync --locked --dev
git switch -c feat/describe-your-change
```

If already cloned, inspect `git status` before updating. Preserve existing changes
and unrelated history. Never force-push or overwrite a conflicting remote.

## Verify a change before pushing

Stage only the files you intend to publish, then run:

```bash
git diff --cached --check
uv run --frozen python scripts/check_publication.py
bash scripts/check.sh
git diff --cached
```

The privacy guard checks the exact Git index, not untracked working files. Its
patterns are heuristic; manual review remains necessary. Never stage mailbox
exports, personalized rules, credentials, tokens, plans, samples, or logs.

After reviewing the source, commit the intended change and push its feature branch.
Open a pull request and verify all three Quality jobs before merging. CI requires
no Gmail OAuth secrets; do not add them to GitHub Actions.

## Release decisions

- Repository visibility was selected by the owner; do not change it automatically.
- No open-source reuse license has been selected. See [LICENSE_NOTICE.md](../LICENSE_NOTICE.md).
- Consider branch protection and private vulnerability reporting before accepting external contributions.
- Create release tags only after the desired checks pass for the exact commit.
- GitHub publication does not authorize a live Gmail purge or establish OAuth app verification.

## Recovery provenance

The original local bundle contains commit `b46088e`. The public import is commit
`756399b`; its tracked tree was verified to match that recovered snapshot.
See [EVIDENCE.md](EVIDENCE.md) for the source-tree identifier and CI evidence.
