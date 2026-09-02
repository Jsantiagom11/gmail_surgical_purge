#!/usr/bin/env python3
"""Scan the exact Git index, not an unrelated working-tree copy, before publication."""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import PurePosixPath

FORBIDDEN_PARTS = {".gmail-purge", "credentials", ".venv", "__pycache__"}
FORBIDDEN_NAMES = (
    "credentials*.json",
    "client_secret*.json",
    "token*.json",
    "*plan*.json",
    "*state*.json",
    "*.local.toml",
    "*.log",
    "*.out",
    "*.mbox",
    "*.eml",
    "*.pem",
    "*.key",
    ".env",
    ".env.*",
)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@([A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63})")
EXAMPLE_DOMAINS = {"example.com", "example.org", "example.net", "users.noreply.github.com"}
SECRETS = (
    re.compile(r"ya29\.[A-Za-z0-9_-]{20,}"),
    re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r'"refresh_token"\s*:\s*"[^"\s]{8,}"'),
)


def inspect_file(name: str, content: bytes) -> tuple[str, ...]:
    path = PurePosixPath(name)
    errors: list[str] = []
    if any(part in FORBIDDEN_PARTS for part in path.parts) or any(
        fnmatch.fnmatch(path.name, pattern) for pattern in FORBIDDEN_NAMES
    ):
        errors.append("private/runtime path")
    if len(content) > 2 * 1024 * 1024:
        return (*errors, "unexpectedly large tracked file")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return (*errors, "unexpected binary content")
    if any(pattern.search(text) for pattern in SECRETS):
        errors.append("possible secret")
    if "@" in text and any(
        match.group(1).lower() not in EXAMPLE_DOMAINS for match in EMAIL.finditer(text)
    ):
        errors.append("non-example email address")
    return tuple(errors)


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], stderr=subprocess.PIPE)


def main() -> int:
    try:
        paths = [name for name in git_bytes("ls-files", "-z").decode().split("\0") if name]
        if not paths:
            print("Publication check failed: the Git index is empty", file=sys.stderr)
            return 1
        problems: list[str] = []
        for path in paths:
            for problem in inspect_file(path, git_bytes("show", f":{path}")):
                problems.append(f"{path}: {problem}")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
        print("Publication check failed: cannot inspect the Git index", file=sys.stderr)
        return 1
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"Publication check passed: {len(paths)} staged files; no detected private payloads")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
