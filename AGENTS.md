# AGENTS.md

This file gives AI coding agents the context they need to work in this
repository safely. Read it, and `CONTRIBUTING.md`, before making changes;
the module docs under `docs/` are the source of truth for each package's
design.

## Project overview

**Mycelium** is a protocol for distributing *encrypted feeds*, hiding
them in plain sight as ordinary files on file-hosting platforms (Gitee,
GitCode/AtomGit). A sower encrypts and signs feed content, disguises it
as an innocuous file inside a forked repository, and hands out obfuscated
spore links; pickers decrypt and verify using only the public
verification key embedded in the link.

- **Content hiding, not anonymity.** Transport security comes from the
  hosting platform's HTTPS; Mycelium does not hide pickers from their
  ISP or the platform. Spore-link obfuscation deters casual observers only.
- **Content publicity follows the link.** With a **public** link, publish
  only public content; a link shared privately with one person or a few
  team members may also carry confidential messages — but confidentiality
  rests entirely on the link staying private, since anyone who can read
  the link can decrypt.
- **Small, tight codebase.** Keep it that way: prefer minimal changes over
  new abstractions, and match existing style exactly.

## Repository layout

| Path                               | Purpose                                                                                                                                                        |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/mycelium/`                    | Source package (`crypto`, `protocol`, `interface`, `utils`)                                                                                                    |
| `src/mycelium/protocol/feed.proto` | Protobuf source of truth; `feed_pb.py` is generated next to it                                                                                                 |
| `docs/`                            | Module docs mirroring the package layout (English + optional `_zh-Hans.md` translations)                                                                       |
| `tests/`                           | Unit tests mirroring the package layout; live platform tests in `tests/interface/`                                                                             |
| `examples/`                        | Runnable end-to-end examples (`eg_publish.py`, `eg_subscribe.py`, `eg_changelog.py`); the generated changelog feed `ChangeLog.dat` is committed as an example  |
| `scripts/`                         | Project scripts outside the package (`gate.py`, the one-command check-and-fix pre-submit gate; `mdtables.py`, the CJK-aware GFM table alignment checker/fixer) |

## Commands

The project is managed with `uv`. All commands below use `uv run`, which
resolves the tool from the project environment and syncs it first if
needed — no activated venv required. Run them from the repository root.
Requires Python ≥ 3.12.

| Task                       | Command                                                                           |
| -------------------------- | --------------------------------------------------------------------------------- |
| Install deps + dev tooling | `uv sync`                                                                         |
| Lint (zero warnings)       | `uv run ruff check .`                                                             |
| Run unit tests             | `uv run pytest`                                                                   |
| Lint Markdown              | `uv run mdlint check --config mdlint.toml . && uv run python scripts/mdtables.py` |
| Realign tables in place    | `uv run python scripts/mdtables.py --fix`                                         |
| Regenerate protobuf        | `uv run buf generate`                                                             |
| Full gate (all checks)     | `uv run python scripts/gate.py`                                                   |

## Architecture

**`mycelium.crypto`** — the cryptography is **deterministic**: the only
source of randomness is the publisher's 32-byte Ed25519 secret key `sk`.
The verification key `vk = get_pub(sk)` derives everything else: the AES
master key `mk = vk2mk(vk)` (PBKDF2) and the XOR pad `pad = vk2pad(vk)`.
AES-256-GCM uses `TIME(6B) * 2` as the nonce; **`(time, edition)` must
never repeat** and GCM objects are single-use (reuse raises
`RuntimeError`).

**`mycelium.protocol`** — `Fruit` / `Sclerotium` structures with the
encrypt/decrypt/verify workflow, `Spore` link addressing (`mycelium://` +
a fake64 string: Base58 with 6 separator chars, disguised as Base64), and
the protobuf wire format. Wire bytes are cyclically XOR-obfuscated with
the pad; `crypto.xor` is self-inverse. Pickers need only `vk` to
decrypt *and* verify.

**`mycelium.interface`** — strict role separation: the sower is
push-only (`Storage.push` ABC; `GitPlatformClient` in `sower/base.py`
is the abstract git-hosting contract — a pure abstract class, every method
a `pass` placeholder and `push` inherited abstract from `Storage`; each
platform module `sower/gitee.py`, `sower/gitcode.py`,
`sower/github.py`, `sower/cnb.py` implements the full lifecycle
itself), the picker is pull-only (`picker/hypha.py`). The namespace is
taken from `GET /user` on every platform **except CNB** (whose namespace
is the organization path — the caller's `group`, or the profile username
when omitted, reusing an existing empty organization if available — CNB
has no personal repositories); access tokens arrive only via runtime
arguments.

**`mycelium.utils`** — Base58, the `fake64` serialization, and misc type
helpers. Project scripts (e.g. `scripts/mdtables.py`, the CJK-aware GFM
table alignment tool) live outside the package.

## Non-negotiables

1. **Do not break cryptographic determinism.** In the crypto layer the
   only source of randomness is `sk`; never reuse a `(time, edition)`
   pair; never reuse a GCM object. Cosmetic randomness elsewhere (e.g.
   the fake64 separator choice in `utils/base58.py`) is allowed as long
   as it never feeds keys, nonces or ciphertext.
2. **`src/mycelium/protocol/feed_pb.py` is generated.** Edit
   `src/mycelium/protocol/feed.proto` and run `uv run buf generate`; never hand-edit the output.
   Code imports it as `from . import feed_pb as pb`.
3. **Never commit credentials.** Tokens exist only as runtime arguments or
   in the gitignored local file `tests/interface/tokens.py` — never in
   source, docs, or fixtures. The `live_*.py` tests take a token from argv
   first and fall back to that local file via `try/except ImportError`.
4. **Respect role separation.** Sowers must not pull and pickers
   must not push; keep the `Storage.push` / `Hypha.pull` contracts clean.
5. **Key files are PEM.** Sowers keep keys as PKCS#8 PEM
   (`Config.export_pem`, passphrase optional). Legacy raw-byte `.dat` keys
   are migration-only, handled in `crypto.load` and the examples — do not
   reintroduce them as a storage format.

## Conventions

- Module files carry the header `# Copyright (c) 2026 demoliisher` +
  `# SPDX-License-Identifier: MIT`.
- Docstrings are rich and narrative; docs live in `docs/` mirroring the
  package layout. The English `README.md` is the source of truth;
  `_zh-Hans.md` translations are optional but must stay in sync.
- Tests are `unittest`-style classes collected by pytest (`testpaths =
  ["tests"]`). The `live_*.py` platform tests are **not** collected — do
  not rename them to `test_*.py`.
- Markdown: MD013 (line length), MD033 (inline HTML) and MD030 (line-
  leading bold) are intentionally disabled — write natural long lines,
  `**...**` at line start, and inline HTML for any advanced feature that
  needs it; never wrap prose to a fixed width. Tables must be GFM-aligned —
  run `uv run python scripts/mdtables.py` after editing one. Chinese
  docs use corner quotes 「」 (『』 for nesting).
- Release workflow: semantic versioning + Conventional Commits; changelog
  updates (`examples/eg_changelog.py` entries + the README "Changelog"
  section) precede any push. Pushing requires explicit user approval:
  before every push, propose a version bump and a summary commit message
  covering all unpushed commits for review.
- Ecosystem naming: the feed message is a *sclerotium*
  (`protocol.Sclerotium`) growing on the hosting platform (*soil*), and
  each of its entries is a *fruit* (`protocol.Fruit`); the sclerotium
  produces the *spore* (`protocol.Spore`) — one canonical `mycelium://`
  link per feed, exports differing only in the cosmetic fake64
  separators, so copies of a link are identical and sharing a link is
  spreading the spore; the picker's puller is the *hypha*
  (`interface.picker.Hypha`). Roles carry ecosystem names and the
  interface packages are named after them: `interface.sower` (the
  publisher, who cultivates the sclerotium and sheds spores) and
  `interface.picker` (the subscriber, who follows the spore's trail back
  to the sclerotium and harvests the fruit). The old names `Node`,
  `Crawler`, the `publisher` / `subscriber` package names and the
  `Item` / `Channel` message names are gone — no compat aliases; always
  use `Spore` / `Hypha` / `Sclerotium` / `Fruit`.
- `README_zh-lzh.md` (the classical Chinese README) is maintained
  **by the author only**. Agents must never read, edit, lint, diff or review
  its content: its wording can trip LLM content-safety mechanisms
  (especially Chinese domestic LLMs). When `git status` shows it modified,
  do not inspect it, and never mention it in the next commit's **title**
  (at most a brief note in the commit body). The pre-submit gate
  (`scripts/gate.py`) checks it but restores it afterwards — it is never
  auto-fixed.
- Sower-identity separation: audit each push — commit authorship and
  history content. Identifiers tied to platforms in regions with stronger
  censorship must never surface on platforms in regions with weaker
  censorship; treat identities as permanently separate (see
  CONTRIBUTING.md).

## Platform quirks

- **Gitee** returns an empty list `[]` for a missing file and defaults to
  branch `master`; **GitCode** returns HTTP 404 for a missing file and
  defaults to branch `main`; **GitHub** returns HTTP 404 for a missing
  file, defaults to branch `main`, authenticates via an `Authorization:
  Bearer` header (not an `access_token` query parameter), and uses a
  single PUT contents endpoint for both create and update.
- Both Gitee and GitCode fork **asynchronously**: a push immediately after
  forking can hit a transient error (Gitee HTTP 400 `文件新建失败`; GitCode
  lock errors). GitHub's fork is likewise async — a write right after
  forking can transiently fail with HTTP 409/422. Sowers retry with a
  backoff (see `GitPlatformClient._WRITE_RETRIES` in `sower/base.py`).
  Do not remove the retry, and do not treat a missing file as a failed
  request.
- `GithubClient` takes a `cdn` argument (bool or callable) that rewrites
  raw `githubusercontent.com` URLs into accelerated mirrors: `True`
  selects the jsDelivr `cdn.jsdelivr.net/gh` mirror, a callable is used
  as-is, and `False` (the default) keeps raw links — keep the default for
  private repositories.
- **CNB** (cnb.cool) has **no personal repositories, no contents write API
  and no fork API**: repositories live inside organizations (the `group`
  constructor argument is optional — when omitted the organization is
  resolved from the profile username: the username-named org when it
  exists, else an existing empty org is reused (`GET /user/groups`,
  `account-engage` scope), else a username-named org is auto-created;
  root-org creation is yearly-quota-limited (web and API alike), HTTP 429), the feed blob is
  written with a real `git push` (username `cnb`, token as password,
  temporary credential store), and `fork` mode raises with a manual-fork
  hint. The API authenticates with `Authorization: Bearer` and the raw
  endpoint requires the token even for public repositories (pickers need
  an authenticated session). OpenAPI deletion of root-org resources is
  refused with HTTP 412 until the web-only setting 允许通过 Open API 删除组织下资源
  (组织设置 → 管控 → 组织管控 → 危险操作) is enabled — `delete_repo` raises a
  `ValueError` with that guidance on 412; the org itself is deleted only
  when empty, and deleting orgs does not free the yearly creation quota —
  treat root organizations as a scarce yearly resource: do not delete
  them unless necessary. The official OpenAPI spec
  (<https://api.cnb.cool/swagger.json>) confirms the platform constraints:
  `root_group_protection` is read-only (absent from the `PUT
  /{slug}/-/settings` body — web-only), sub-organizations are read-only
  (`GET /user/groups/{slug}`, `GET /{slug}/-/sub-groups`; no create
  endpoint, so the yearly root-org quota cannot be bypassed), the only
  git write endpoint is `POST /{repo}/-/git/blobs` (no tree/commit/ref
  writes — a real git push is the only write path), there is no
  fork-creation endpoint, and the `x-cnb-identity-ticket` header (WeChat
  auth ticket, returned on the first attempt) gates `DELETE` on
  repositories, organizations, missions and registries alike.
  Its `_write_file` raises (no contents API) and `push` retries transient
  git failures itself.
- `Spore.parse` tolerates a missing header, and obfuscation is not
  encryption — treat spore-link fields as public.

## Common pitfalls

- `Sclerotium.encrypt` mutates `sclerotium.time` (refreshing the
  timestamp per encryption); `Sclerotium.decrypt` also accepts a raw
  `pb.Sclerotium`.
- Pass the derived `mk` into `Fruit.decrypt` (via `Sclerotium.decrypt`)
  instead of re-running PBKDF2 per fruit.
- pycryptodome's `export_key(format="PEM")` returns a **str** — encode it
  before writing bytes.
- Git may warn about CRLF on diff — cosmetic on Windows (autocrlf).

## Before submitting

Run the full gate — one command checks and auto-fixes code style, tests,
markdown lint and table alignment (also documented in `CONTRIBUTING.md`):

| Check           | Command                         |
| --------------- | ------------------------------- |
| Full gate       | `uv run python scripts/gate.py` |

When in doubt, read `CONTRIBUTING.md` and the module docs under `docs/`
before changing code.
