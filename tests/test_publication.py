from pathlib import Path
from unittest.mock import patch

from scripts.check_publication import inspect_file, main


def test_reserved_examples_are_allowed() -> None:
    assert inspect_file("README.md", b"demo@example.com") == ()
    assert inspect_file("src/example.py", b"print('hello')") == ()


def test_private_paths_and_payloads_rejected() -> None:
    assert "private/runtime path" in inspect_file(".gmail-purge/plan.json", b"{}")
    assert "private/runtime path" in inspect_file("config.local.toml", b"x=1")
    assert "non-example email address" in inspect_file(
        "README.md", ("someone@" + "provider.invalid").encode()
    )
    assert "possible secret" in inspect_file("data.txt", ("ya29." + "x" * 40).encode())
    assert "unexpected binary content" in inspect_file("binary.bin", b"\xff")
    assert "unexpectedly large tracked file" in inspect_file(
        "big.txt", b"a" * (2 * 1024 * 1024 + 1)
    )


def test_index_scan_pass_fail_and_empty() -> None:
    with patch("scripts.check_publication.git_bytes", side_effect=[b"README.md\0", b"safe"]):
        assert main() == 0
    with patch("scripts.check_publication.git_bytes", side_effect=[b"token.json\0", b"{}"]):
        assert main() == 1
    with patch("scripts.check_publication.git_bytes", return_value=b""):
        assert main() == 1
    with patch("scripts.check_publication.git_bytes", side_effect=OSError):
        assert main() == 1


def test_plan_no_clobber_race_is_atomic(tmp_path: Path) -> None:
    import pytest

    from gmail_surgical_purge.errors import SafetyError
    from gmail_surgical_purge.storage import write_private_text

    with (
        patch("gmail_surgical_purge.storage.os.link", side_effect=FileExistsError),
        pytest.raises(SafetyError, match="concurrently"),
    ):
        write_private_text(tmp_path / "plan.json", "{}", overwrite=False)
