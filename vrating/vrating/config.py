"""Settings from the environment, plus a `.env` for the ones you always want.

This is a single-person tool, and the accounts it is about do not change from run to run.
Naming them once in `.env` means every entry point -- the server, the warmer, the page you
open -- starts from the same list without anyone retyping it.

`.env` never wins over a real environment variable, so `VRATING_HANDLES=someone_else` on the
command line still overrides the file for one run.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HANDLES = "VRATING_HANDLES"
AC_HANDLES = "VRATING_AC_HANDLES"


def load_env(path=None, override: bool = False) -> dict:
    """Read `KEY=VALUE` lines into os.environ and return what the file held.

    Deliberately small: no interpolation, no inline comments (put `#` on its own line), no
    multi-line values. Anything richer belongs in a real config file, not in the thing that
    holds two lists of handles.
    """
    path = Path(path or os.environ.get("VRATING_ENV") or ROOT / ".env")
    found: dict[str, str] = {}
    try:
        text = path.read_text()
    except OSError:
        return found
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        found[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return found


def _split(text: str) -> list[str]:
    from .career.engine import parse_handles
    return parse_handles(text or "")


def handles() -> list[str]:
    """The Codeforces accounts this instance is about, in the order they were listed.

    Exactly as written in `.env`: renames are not resolved here, because that costs an API
    call and most callers only want to know whether anything was configured at all. Ask
    `engine.canonical_handles` when the identities have to be right.
    """
    return _split(os.environ.get(HANDLES, ""))


def ac_handles() -> list[str]:
    """The AtCoder accounts. Separate list: AtCoder handles are their own namespace."""
    return _split(os.environ.get(AC_HANDLES, ""))
