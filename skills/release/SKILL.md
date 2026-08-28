---
name: mycelium-release
description: Mycelium release workflow — version decision, changelog sync, gate, identity audit, mandatory user approval, commit + tag + push.
---

# mycelium-release

Run this skill whenever a release (tagged push) is requested or when
uncommitted work needs to ship. It encodes the full release SOP so any
agent (or human) performs every step in order without skipping the
project's guardrails.

Rules of record: `AGENTS.md` (conventions, non-negotiables, identity
audit) and `CONTRIBUTING.md`. This skill restates the *flow*, never the
rules — read those files first.

## When to use

- A versioned push is requested (`vX.Y.Z`).
- The working tree contains changes that need to ship to `origin/main`.

## Procedure

- **1. Read the ground rules.** Read `AGENTS.md` and `CONTRIBUTING.md`
  before anything else.
- **2. Decide the version bump** (user may override, as with 0.3.0 →
  0.2.1): `feat` (new capability) → minor bump; `fix` / `docs` (behavior
  or documentation only) → patch bump. Confirm the target version with
  the user before proposing the commit.
- **3. Sync the changelog** (must precede the push):
  - add the entry to the "Changelog" section of `README.md` (EN) and
    `README_zh-Hans.md` (zh-Hans, corner quotes 「」);
  - add the matching entry to `examples/eg_changelog.py`;
  - regenerate the example feed with
    `uv run python examples/eg_changelog.py` (updates
    `examples/ChangeLog.dat`; the canonical spore link must stay stable —
    never hand-edit the `.dat`).
- **4. Run the full gate**: `uv run python scripts/gate.py` — fix
  anything it flags and re-run until green.
- **5. Audit identity**:
  - `git config user.name` / `user.email` must be `demoliisher` /
    `txpbyy@proton.me`;
  - review the diff for forbidden identifiers (RainbowHat / rainbowhat /
    小虹帽) — runtime-printed usernames do not count as commit content;
  - `README_zh-lzh.md` must never be read, modified or mentioned in the
    commit **title** (at most a body note); if `git status` shows it
    modified, leave it alone.
- **6. Propose and wait.** Present the version number and the full
  commit message (title + body covering all unpushed commits) to the
  user and **wait for explicit approval** — every push requires it. Do
  not push without this step.
- **7. Commit and tag** (after approval):
  - `git add -A`; verify the staged list;
  - write the commit message to a UTF-8 (no BOM) temp file and use
    `git commit -F <file>` (avoids Windows console encoding issues);
  - `git tag vX.Y.Z`.
- **8. Push** both branch and tag (`git push origin main`, then
  `git push origin vX.Y.Z`); confirm with `git log --oneline -3` and the
  push output.
