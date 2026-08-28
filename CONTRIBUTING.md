# Contributing to Mycelium

Thanks for helping out. Mycelium is a protocol for distributing encrypted
feeds, disguised as ordinary files on file-hosting platforms. The
repository is small and the codebase is kept intentionally tight — read the
module docs under `docs/` (each ships in English; translations are
optional) before touching a package.

## Contributing workflow

This project follows the standard GitHub fork-and-pull model. All changes
land on `main` through pull requests — never push directly to `main`.

1. **Fork the repository.** Use the "Fork" button on GitHub to create a
   copy under your own account, then clone it locally:

   ```text
   git clone https://github.com/<you>/Mycelium.git
   cd Mycelium
   git remote add upstream https://github.com/demoliisher/Mycelium.git
   ```

   Note: the *development* fork above is ordinary GitHub collaboration.
   Do not confuse it with Mycelium's `fork` publisher mode — that mode is
   a product feature (disguising a feed as a forked repository) and has
   nothing to do with contributing code.

2. **Create a topic branch.** One logical change per branch, branched off
   the latest `main`:

   ```text
   git fetch upstream
   git checkout -b fix/your-branch-name upstream/main
   ```

3. **Commit with Conventional Commits.** Follow the existing style
   (`feat:`, `fix:`, `docs:`, ...); see Versioning & releases below.

4. **Run the full gate before pushing** (see Before submitting): `ruff`,
   `pytest`, `mdlint` and `mdtables` must all pass.

5. **Push and open a pull request.** Push the branch to your fork and
   open a PR against `demoliisher/Mycelium:main`. In the description,
   briefly state what the change does, why, and how it was tested; if it
   fixes an issue, reference it (e.g. `Closes #123`). Keep PRs small and
   focused — one topic per PR is far easier to review than a bundle of
   unrelated changes.

6. **Review.** Maintainers review your PR and may ask for changes — reply
   in the PR thread and push follow-up commits to the same branch; do not
   force-push a branch after it has been reviewed (prefer adding commits
   to rewriting history). Once approved and merged, delete the topic
   branch.

Use a consistent public identity for your commits. For large or
design-level changes, open an issue first to discuss the approach before
writing code; first-time contributors are welcome to pick a good-first
issue.

## Setup

- Python **≥ 3.12**.
- The project is managed with `uv` (a `uv.lock` is committed). Install the
  project plus dev tooling with:

  ```text
  uv sync
  ```

  The dev group provides `ruff`, `pytest`, `markdownlint-rs` (`mdlint`),
  `buf` and `protoc-gen-py`. All commands below use `uv run`, which
  resolves each tool from the project environment and syncs it first if
  needed — no activated venv required.

## Code style

- **`uv run ruff check .`** must pass with zero warnings (default rule set).
- `src/mycelium/protocol/feed_pb.py` is **generated code** — never edit it
  by hand. The source of truth is `src/mycelium/protocol/feed.proto`;
  regenerate with `uv run buf generate` (configuration: `buf.gen.yaml`)
  after changing the proto and commit the regenerated file. Code imports
  it as `from . import feed_pb as pb`.

## Tests

- **`uv run pytest`** must pass (the suite currently has 150 tests; `testpaths`
  is configured in `pyproject.toml`).

## Documentation

Module documentation lives in `docs/`, mirroring the package layout: a
package with sub-modules gets a folder with a `README.md` overview plus
one document per module named after it (`docs/crypto/README.md` +
`Hash.md`/`AES.md`/`EdDSA.md`; the sower platform documents live at
`docs/interface/sower/<platform>.md`), while a module without sub-modules
is a single file (`docs/interface/picker.md`). The English file is
**required** — it is the source of truth. Translations are **optional**:
you are welcome to add or update one (Simplified Chinese uses the
`<module>_zh-Hans.md` naming; other languages follow the same `<lang>`
suffix pattern). If a translation exists, keep it in sync with the
English original.

Every documentation change must pass:

1. **Markdown lint, in two commands** — first
   `uv run mdlint check --config mdlint.toml .` (markdownlint-rs with the
   repository config), then `uv run python skills/gate/scripts/mdtables.py` (GFM table
   column alignment, the MD060 "aligned" style, CJK-width aware). Two notes
   on the markdownlint-rs config: MD033 (inline HTML) and MD030 (list
   marker spacing) are **intentionally disabled** (MD030 because
   markdownlint-rs mis-parses line-leading `**` as a `*` list marker — do
   not work around rules by rewriting prose; line-leading bold is written
   as `**...**`; inline HTML is allowed for any advanced feature that needs
   it, not only tables — the GitCode permission table is one example: an
   HTML table with a rowspan-merged level column and colored
   read/write/forbid recommendations). MD013 (line length) is **disabled
   entirely**: prose is written as natural long lines, because wrapping
   (especially CJK) text to a fixed width inserts spurious spaces when
   rendered. After editing any table, run
   `uv run python skills/gate/scripts/mdtables.py --fix` to realign in place, then
   re-check.

Writing conventions:

- Tables use GFM pipe syntax; the alignment tool keeps columns visually
  aligned (East Asian wide characters count as two columns).
- Links to a translation use the `<lang>` suffix, e.g. `*_zh-Hans.md`.

## Versioning & releases

- Versions follow **semantic versioning** (`major.minor.patch`).
- Commit messages follow the **Conventional Commits** standard (`feat:`,
  `fix:`, `docs:`, ...).
- The project's changelog lives in two mirrored places: the `entries` list
  of `examples/eg_changelog.py` (one `(version, entry)` tuple per release)
  and the "Changelog" section of the `README.md`. Update both, then run
  `uv run python examples/eg_changelog.py` to regenerate the committed
  example feed `examples/ChangeLog.dat`.
- Audit what a push will publish before doing it — pushing makes history
  permanent. Check the commit author identity and every identifier inside
  the history (usernames, emails, account names, hosting paths). Keep
  identities separate: identifiers tied to platforms in regions with
  stronger censorship must never surface on platforms in regions with
  weaker censorship. If a leak slips through, rewrite the history and
  force-push before the branch is shared further.

## Before submitting

Run the full gate with one command — it checks and auto-fixes code style
(ruff), tests (pytest), markdown lint (mdlint) and table alignment
(mdtables):

| Check           | Command                                     |
| --------------- | ------------------------------------------- |
| Full gate       | `uv run python skills/gate/scripts/gate.py` |
