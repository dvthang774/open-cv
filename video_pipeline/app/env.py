from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")


def load_env_file(path: str | os.PathLike) -> None:
    """
    Minimal .env loader (no external deps).
    - Supports KEY=VALUE
    - Ignores empty lines and lines starting with '#'
    - Does not override existing os.environ values
    """
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def get_env(key: str, default: T, cast: Callable[[str], T] | None = None) -> T:
    val = os.getenv(key)
    if val is None or val == "":
        return default
    if cast is None:
        return val  # type: ignore[return-value]
    return cast(val)

