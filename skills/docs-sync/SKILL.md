---
name: mycelium-docs-sync
description: Keep Mycelium documentation in sync — English source of truth, zh-Hans translation, table alignment, changelog triple-sync, classical-Chinese no-go zone.
---

# mycelium-docs-sync

Mycelium documentation follows strict sync rules. This skill is the
checklist for editing any documentation: when to touch which file, how
to keep the two languages in sync, and what to never touch.

Rules of record: `AGENTS.md` ("Conventions"). This skill restates the
*workflow*.

## File roles

- `README.md` (EN) — the **source of truth**; write content here first.
- `README_zh-Hans.md` — translation; must stay in sync (corner quotes
  「」, 『』 for nesting).
- `docs/` — module docs mirroring `src/mycelium/`; each package's design
  lives here (EN + optional `_zh-Hans.md`).
- `README_zh-lzh.md` (classical Chinese) — **author-only**. Never read,
  edit, lint, diff or review it; its wording can trip LLM content-safety
  mechanisms. If `git status` shows it modified, leave it alone and never
  mention it in a commit title.

## Checklist for a docs edit

- **1. Write EN first** (source of truth), then mirror in zh-Hans.
- **2. Chinese conventions**: corner quotes 「」 (『』 for nesting);
  never wrap prose to a fixed width — MD013 (line length), MD033
  (inline HTML) and MD030 (line-leading bold) are intentionally
  disabled, so write natural long lines and `**...**` at line start
  freely.
- **3. Tables must be GFM-aligned**: run
  `uv run python scripts/mdtables.py --fix` after editing any table,
  and verify with the plain check.
- **4. Changelog triple-sync** (for releases):
  - "Changelog" section of `README.md` and `README_zh-Hans.md`;
  - `examples/eg_changelog.py` entry;
  - regenerate `examples/ChangeLog.dat` with
    `uv run python examples/eg_changelog.py` — the canonical spore link
    must stay stable.
- **5. Run the full gate** (`uv run python scripts/gate.py`) after any
  docs change.
