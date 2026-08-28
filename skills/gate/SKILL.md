---
name: gate
description: Pre-submit gate for Mycelium — run the one-command check-and-fix gate, handle failures, and audit identity before any commit.
---

# gate

Run before every commit or push. The gate is a single command that
checks code style, unit tests, markdown lint and table alignment, and
auto-fixes what it can. This skill covers *when* to run it, how to
handle failures, and the identity audit that the gate does not perform.

Ground rules: `AGENTS.md` ("Before submitting") and `CONTRIBUTING.md`.

## When to use

- Before staging/committing any change.
- After editing markdown tables, docs, or generated files.

## Procedure

- **1. Run the gate**: `uv run python skills/gate/scripts/gate.py`
  from the repository root — the project scripts live in this skill's
  `scripts/` directory. It runs, in order:
  - `uv run ruff check . --fix` (code style, auto-fixed);
  - `uv run pytest -q` (unit tests; must end green);
  - `uv run mdlint check --config mdlint.toml . --fix` (markdown lint);
  - `uv run python skills/gate/scripts/mdtables.py --fix` + verify (GFM
    table alignment).
- **2. On failure**, fix the flagged issue and re-run the whole gate:
  - lint errors the gate cannot auto-fix (e.g. MD034 bare URLs — wrap
    in `<...>`) must be fixed by hand;
  - test failures: investigate before proceeding; never commit a red
    gate.
- **3. Identity audit** (the gate does not cover this):
  - commit author must be `demoliisher <txpbyy@proton.me>`;
  - staged content must not introduce RainbowHat / rainbowhat / 小虹帽;
  - `README_zh-lzh.md` is checked by the gate but restored afterwards —
    agents never read, edit, lint, diff or review it, and never mention
    it in a commit title.
- **4. Commit only when the gate is fully green.**
