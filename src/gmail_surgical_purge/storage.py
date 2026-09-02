"""Private, atomic local artifacts and a POSIX single-process lock."""

from __future__ import annotations

import fcntl
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .errors import PurgeError, SafetyError

ModelT = TypeVar("ModelT", bound=BaseModel)
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def write_private_text(path: Path, content: str, *, overwrite: bool = True) -> None:
    if path.is_symlink():
        raise SafetyError("Refusing to write through a symlink")
    if path.exists() and not overwrite:
        raise SafetyError(
            "Output already exists. Use a new path; reviewed plans are not overwritten."
        )
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            try:
                # Same-directory hard-link creation is atomic and cannot clobber a rival plan.
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError as exc:
                raise SafetyError("Output was created concurrently; use a new path") from exc
            temporary.unlink()
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def write_model(path: Path, model: BaseModel, *, overwrite: bool = True) -> None:
    write_private_text(path, model.model_dump_json(indent=2) + "\n", overwrite=overwrite)


def read_model(path: Path, model_type: type[ModelT]) -> ModelT:
    try:
        if path.is_symlink() or path.stat().st_size > MAX_ARTIFACT_BYTES:
            raise SafetyError("Refusing symlink or oversized local artifact")
        return model_type.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise PurgeError(f"Invalid or unreadable {model_type.__name__} artifact") from exc


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise SafetyError("Cannot open the process lock safely") from exc
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SafetyError("Another process is using this data directory") from exc
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)
