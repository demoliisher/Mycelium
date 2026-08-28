---
name: platform-add
description: Add a new storage backend to Mycelium — a git-hosting platform (subclass GitPlatformClient) or a non-git storage service (subclass Storage) — with contract, docs, live tests and identity audit.
---

# platform-add

Mycelium is **not git-only**: the sower side supports git-hosting
platforms (Gitee, GitCode, GitHub, CNB) *and* plain storage services
(e.g. WebDAV). Adding a backend means implementing one of two contracts.
This skill is the full checklist.

Rules of record: `AGENTS.md` (architecture, platform quirks, identity
audit) and `docs/interface/sower/README.md` ("Adding a Platform").

## Two backend kinds

- **Git-hosting platform** — subclass `GitPlatformClient`
  (`src/mycelium/interface/sower/base.py`), a pure abstract class:
  implement the constructor, the class attributes and every abstract
  method; `push` is inherited abstract from `Storage` and must be
  implemented. New modules sit next to `gitee.py` / `gitcode.py` /
  `github.py` / `cnb.py` and are exported from `sower/__init__.py`.
- **Non-git storage service** — subclass `Storage` directly and
  implement `push` (no git, no fork, no namespace contract).

## Checklist

1. **Read the platform contract** in
   `docs/interface/sower/README.md` — every abstract method, the
   namespace rule (`GET /user` on every platform **except CNB**, whose
   namespace is the organization path), and the platform quirks section
   of `AGENTS.md` (add your platform's quirks there too).
2. **Implement the module** matching existing style exactly (module
   header, narrative docstring, error behavior).
3. **Token scopes**: document the exact authorization scopes the
   platform token needs in the README permission table (EN + zh-Hans).
4. **Unit tests**: `tests/interface/test_<platform>.py` with
   `unittest`-style classes (collected by pytest).
5. **Live smoke test**: `tests/interface/live_<platform>.py` — **not**
   collected; never rename it to `test_*.py`. Token from argv first,
   fall back to the gitignored `tests/interface/tokens.py`.
6. **Docs**: README (EN source of truth + zh-Hans), module docs,
   AGENTS.md quirks entry.
7. **Identity audit**: platform identities are permanently separate —
   identifiers tied to platforms in regions with stronger censorship
   must never surface on platforms in weaker ones.
8. **Run the full gate** (`uv run python scripts/gate.py`) before
   committing; follow the release skill for shipping.
