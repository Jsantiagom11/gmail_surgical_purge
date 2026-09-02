# Publishing checklist

The repository is prepared locally. A GitHub repository and successful remote CI
must be verified separately; this document is not proof of publication.

## Owner decisions

- Choose repository visibility deliberately. Private is the safer staging option.
- Choose a license if you intend to grant reuse rights; none is granted by this template.
- Do not add Gmail OAuth secrets to GitHub Actions. CI is entirely offline with synthetic mail.

## Verify the exact source before pushing

```bash
git status --short
git diff --check
uv run --frozen python scripts/check_publication.py
bash scripts/check.sh
```

The privacy check reads the Git index, including staged content. Review `git diff
--cached` as well. No regular-expression scan can guarantee the absence of personal data.

## Publish from an authenticated Linux/WSL2 environment

If you received a Git bundle, clone it first:

```bash
git clone gmail-surgical-purge.bundle gmail-surgical-purge
cd gmail-surgical-purge
```

The following command creates a **private** repository in the account currently
authenticated by GitHub CLI. Inspect `gh api user --jq .login` before running it.

```bash
gh auth status
gh api user --jq .login
gh repo create gmail-surgical-purge --private --source=. --remote=origin --push
```

If an empty repository already exists, use its verified URL instead:

```bash
git remote add origin https://github.com/YOUR_ACCOUNT/gmail-surgical-purge.git
git push -u origin main
```

Do not overwrite an existing `origin`, force-push, or replace another repository's
history. Inspect a conflicting remote or non-empty destination first.

## After push

1. Confirm GitHub shows the same commit as `git rev-parse HEAD`.
2. Verify the Python 3.11, 3.12, and 3.13 CI jobs; do not infer success from local tests.
3. Configure branch protection and private vulnerability reporting if available.
4. Set topics such as `python`, `gmail-api`, `cli`, `automation`, `email`, `productivity`.
5. Review all source/history and the license decision before changing visibility to public.
6. Create a release tag only after the desired gates are green.
