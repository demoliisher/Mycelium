# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Markdown table alignment checker: the MD060 "aligned" style.

The bundled markdownlint-rs (``mdlint``) cannot enforce the ``aligned``
table style — its MD060 compares the configured style string against
per-column alignment values parsed from ``:`` markers in the delimiter row
(``center``/``right``/``left``/``default``), so ``aligned`` never matches
any table. This script provides the check instead: every GFM table in the
scanned markdown files must have its pipe characters vertically aligned by
*visual* width (CJK and full-width characters count as two columns).

Usage:

    python scripts/mdtables.py                  # check; exit 1 on any misaligned table
    python scripts/mdtables.py --fix            # realign tables in place
    python scripts/mdtables.py path/to/*.md     # scan specific files/dirs

The default scan covers every ``*.md`` under the current directory except
tool and artifact directories (``.venv``, ``.git``, ``.pytest_cache``,
``.uv-cache``, ...). Escaped pipes (``\\|``) inside cells are preserved;
alignment width counts them as two columns.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

__all__ = ["visual_width", "check_text", "fix_text", "discover_markdown"]

# East Asian Width categories rendered at double width (CJK + fullwidth).
_WIDE = ("W", "F")

# Directories never scanned (toolchains, VCS metadata, caches).
_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
}

# A GFM table delimiter row: dashes (optionally wrapped in ':' alignment
# markers) separated by pipes. Requires at least one pipe, so a bare `---`
# horizontal rule is never treated as a table.
_DELIMITER_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$"
)

_FENCE_RE = re.compile(r"^\s*(```|~~~)")

_INDENT = ("    ", "\t")


@dataclass(frozen=True)
class Violation:
    """A misaligned table at ``line`` (1-based) in a file."""

    line: int
    message: str


@dataclass
class _Table:
    """A parsed GFM table block (0-based line indices)."""

    start: int  # header row
    end: int  # last row (exclusive)
    rows: list[list[str]]  # stripped cell texts per row
    has_leading: bool  # rows start with a pipe
    has_trailing: bool  # rows end with a pipe


def visual_width(text: str) -> int:
    """Visual display width: CJK / full-width characters count as 2 columns."""
    return sum(
        2 if unicodedata.east_asian_width(ch) in _WIDE else 1 for ch in text
    )


def discover_markdown(paths: list[str] | None = None) -> list[Path]:
    """
    All ``*.md`` files under ``paths`` (default: current directory).

    Tool and artifact directories (see ``_EXCLUDED_DIRS``) are skipped;
    gitignored files (e.g. the local-only ``*_zh-Hans.md`` docs) are checked.
    """
    roots = [Path(p) for p in paths] if paths else [Path.cwd()]
    files: set[Path] = set()
    for root in roots:
        if root.is_file():
            if root.suffix.lower() == ".md":
                files.add(root)
            continue
        for candidate in root.rglob("*.md"):
            if any(part in _EXCLUDED_DIRS for part in candidate.parts):
                continue
            files.add(candidate)
    return sorted(files)


def _split_row(line: str, has_leading: bool, has_trailing: bool) -> list[str]:
    """Split a table row into stripped cell texts on unescaped pipes."""
    parts = re.split(r"(?<!\\)\|", line)
    if has_leading and parts and not parts[0].strip():
        parts = parts[1:]
    if has_trailing and parts and not parts[-1].strip():
        parts = parts[:-1]
    return [part.strip() for part in parts]


def _parse_tables(lines: list[str]) -> list[_Table]:
    """Extract GFM table blocks, skipping fenced and indented code."""
    tables: list[_Table] = []
    in_fence = False
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        if _FENCE_RE.match(raw) and not raw.startswith(_INDENT):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence or not raw.strip() or raw.startswith(_INDENT):
            i += 1
            continue
        if "|" in raw and i + 1 < n:
            nxt = lines[i + 1]
            if _DELIMITER_RE.match(nxt) and "|" in nxt:
                # rows = [header, delimiter, body...] so that row offsets map
                # 1:1 onto the source lines (start + offset).
                rows = [raw, nxt]
                j = i + 2
                while j < n:
                    row = lines[j]
                    if (
                        not row.strip()
                        or "|" not in row
                        or _FENCE_RE.match(row)
                        or row.startswith(_INDENT)
                    ):
                        break
                    rows.append(row)
                    j += 1
                has_leading = rows[0].lstrip().startswith("|")
                has_trailing = rows[0].rstrip().endswith("|")
                cell_rows = [
                    _split_row(row, has_leading, has_trailing) for row in rows
                ]
                tables.append(
                    _Table(i, j, cell_rows, has_leading, has_trailing)
                )
                i = j
                continue
        i += 1
    return tables


def _column_widths(rows: list[list[str]], ncols: int) -> list[int]:
    widths = [0] * ncols
    for offset, row in enumerate(rows):
        for col, cell in enumerate(row[:ncols]):
            if offset == 1:  # delimiter row: marker cells carry their own width
                cell = cell.strip()
                widths[col] = max(widths[col], visual_width(cell) if cell else 3)
            else:
                widths[col] = max(widths[col], visual_width(cell))
    # GFM requires at least three dashes per delimiter column.
    return [max(3, width) for width in widths]


def _delimiter_cell(original: str, width: int) -> str:
    """Rebuild a delimiter cell at the column width, preserving ':' markers."""
    cell = original.strip()
    left = cell.startswith(":")
    right = cell.endswith(":")
    dashes = width - (1 if left else 0) - (1 if right else 0)
    if dashes < 3:
        dashes = 3
    return (":" if left else "") + "-" * dashes + (":" if right else "")


def _expected_row(
    cells: list[str],
    widths: list[int],
    is_delim: bool,
    has_leading: bool,
    has_trailing: bool,
) -> str:
    """The canonical aligned form of a row (pipes at equal visual columns)."""
    parts: list[str] = []
    for col, cell in enumerate(cells[: len(widths)]):
        if is_delim:
            parts.append(_delimiter_cell(cell, widths[col]))
        else:
            parts.append(cell + " " * (widths[col] - visual_width(cell)))
    inner = " | ".join(parts)
    return (
        (("| " if has_leading else "") + inner + (" |" if has_trailing else ""))
        .rstrip()
    )


def _table_issues(
    table: _Table, lines: list[str]
) -> list[tuple[int, str]]:
    """(line, message) pairs for a table: inconsistent columns or misaligned rows."""
    ncols = len(table.rows[0])
    for row in table.rows:
        if len(row) != ncols:
            return [
                (
                    table.start + 1,
                    "table has inconsistent column counts; not aligned",
                )
            ]
    widths = _column_widths(table.rows, ncols)
    issues: list[tuple[int, str]] = []
    for offset, row in enumerate(table.rows):
        expected = _expected_row(
            row, widths, is_delim=(offset == 1),
            has_leading=table.has_leading, has_trailing=table.has_trailing,
        )
        if lines[table.start + offset].rstrip() != expected:
            issues.append(
                (table.start + offset + 1, "table column not aligned")
            )
    return issues


def check_text(text: str) -> list[Violation]:
    """Return the misalignment violations of every table in ``text``."""
    lines = [line.rstrip("\r\n") for line in text.splitlines(keepends=True)]
    return [
        Violation(line, message)
        for table in _parse_tables(lines)
        for line, message in _table_issues(table, lines)
    ]


def fix_text(text: str) -> tuple[int, str]:
    """
    Realign every table in ``text``.

    Returns ``(fixed_tables, new_text)``. Files without tables are returned
    unchanged.
    """
    raw_lines = text.splitlines(keepends=True)
    lines = [line.rstrip("\r\n") for line in raw_lines]
    tables = _parse_tables(lines)
    if not tables:
        return 0, text
    newline = "\r\n" if "\r\n" in text else "\n"
    rebuilt = list(raw_lines)
    fixed = 0
    for table in reversed(tables):  # bottom-up keeps indices valid
        ncols = len(table.rows[0])
        if any(len(row) != ncols for row in table.rows):
            continue
        widths = _column_widths(table.rows, ncols)
        changed = False
        for offset, row in enumerate(table.rows):
            expected = _expected_row(
                row, widths, is_delim=(offset == 1),
                has_leading=table.has_leading, has_trailing=table.has_trailing,
            )
            if lines[table.start + offset].rstrip() != expected:
                changed = True
            rebuilt[table.start + offset] = expected + newline
        fixed += int(changed)
    return fixed, "".join(rebuilt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/mdtables.py",
        description=(
            "Check or realign GFM tables in markdown files "
            "(the MD060 'aligned' style, CJK-width aware)."
        ),
    )
    parser.add_argument(
        "paths", nargs="*",
        help="files or directories to scan (default: current directory)",
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="rewrite misaligned tables in place instead of reporting",
    )
    args = parser.parse_args(argv)

    issues = 0
    for path in discover_markdown(args.paths):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"{path}: skipped (not UTF-8)")
            continue
        if args.fix:
            fixed, new_text = fix_text(text)
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
                print(f"{path}: realigned {fixed} table(s)")
        else:
            for violation in check_text(text):
                print(f"{path}:{violation.line}: {violation.message}")
                issues += 1

    if not args.fix and issues:
        print(
            f"\n{issues} misaligned table(s); "
            "run 'python scripts/mdtables.py --fix' to realign"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
