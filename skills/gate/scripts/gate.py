# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Full pre-submit gate: check everything, auto-fix what can be fixed.

Run from the repository root:

    uv run python skills/gate/scripts/gate.py

Every step checks and fixes where possible: code style (``ruff check
--fix``), markdown lint (``mdlint check --fix``) and table alignment
(``skills/gate/scripts/mdtables.py --fix``); tests (``pytest``) run as-is. Each
command's output streams to the terminal as the diagnostic log, and the
gate exits non-zero if anything is still broken after fixing. The
classical Chinese README (``README_zh-lzh.md``) is author-only: the gate
checks it but never auto-fixes it, restoring its content if a fixing
step touched it. Run the gate before every conversation wrap-up and
before every commit.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# The classical Chinese README is maintained by the author only (see
# AGENTS.md); fix-capable markdown steps must never rewrite it.
_PROTECTED = Path("README_zh-lzh.md")

# (label, argv, protect?) tuples; fix-capable steps carry the fixing
# flags. Each command is the documented ``uv run`` form.
STEPS: list[tuple[str, list[str], bool]] = [
    ("Code style", ["uv", "run", "ruff", "check", ".", "--fix"], False),
    ("Tests", ["uv", "run", "pytest", "-q"], False),
    (
        "Markdown lint",
        ["uv", "run", "mdlint", "check", "--config", "mdlint.toml", ".", "--fix"],
        True,
    ),
    (
        "Table alignment",
        ["uv", "run", "python", "skills/gate/scripts/mdtables.py", "--fix"],
        True,
    ),
    (
        "Table alignment (verify)",
        ["uv", "run", "python", "skills/gate/scripts/mdtables.py"],
        False,
    ),
]


def _run(label: str, argv: list[str], protect: bool) -> int:
    print(f"\n=== {label}: {' '.join(argv)} ===", flush=True)
    before = (
        _PROTECTED.read_bytes() if protect and _PROTECTED.exists() else None
    )
    result = subprocess.run(argv)
    if before is not None:
        after = _PROTECTED.read_bytes() if _PROTECTED.exists() else None
        if after != before:
            _PROTECTED.write_bytes(before)
            print(
                f"note: restored {_PROTECTED.name} (author-only, never auto-fixed)",
                flush=True,
            )
    return result.returncode


def main() -> int:
    failed: list[str] = []
    for label, argv, protect in STEPS:
        if _run(label, argv, protect) != 0:
            failed.append(label)
    if failed:
        print(
            f"\nGate FAILED: {', '.join(failed)}. Fix the remaining issues "
            "and re-run `uv run python skills/gate/scripts/gate.py`.",
            file=sys.stderr,
        )
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
