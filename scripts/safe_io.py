"""Small, dependency-free helpers for durable JSON writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write a text file atomically in the destination directory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        finally:
            raise


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    indent: int | None = None,
    compact: bool = False,
) -> None:
    kwargs: dict[str, Any] = {"ensure_ascii": False}
    if compact:
        kwargs["separators"] = (",", ":")
    else:
        kwargs["indent"] = indent
    atomic_write_text(Path(path), json.dumps(payload, **kwargs) + "\n")
