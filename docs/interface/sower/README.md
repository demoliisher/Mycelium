# Sower Interface

The sower side of Mycelium: push the encrypted feed blob into a
hosting backend so pickers can pull it.

## Storage Contract

> Source: [base.py](../../../src/mycelium/interface/sower/base.py)

`Storage` is the push-only abstract contract shared by every platform.
There is deliberately no `pull`: fetching is picker behavior (see
`mycelium.interface.picker`), and a sower that wants to read back
what it pushed should call the picker interface itself.

```python
from abc import ABC, abstractmethod

class Storage(ABC):
    @abstractmethod
    def push(self, path: str, data: bytes) -> None:
        """Create or overwrite ``path`` with ``data``."""
        pass
```

## GitPlatformClient Contract

> Source: [base.py](../../../src/mycelium/interface/sower/base.py)

`GitPlatformClient(Storage)` is the abstract contract shared by the
git-hosting platform clients. Like `Storage` itself, it is a pure contract:
every method below is a `pass` placeholder and `push` is deliberately **not**
redefined — it stays abstract from `Storage`, which keeps this class
abstract (it cannot be instantiated). Each platform module implements the
full lifecycle itself, so a platform client is self-contained. A client
must provide:

- the constructor: `access_token` plus **exactly one** of `repo` / `fork`
  (mutually exclusive; fork mode targets the source's name), `branch`
  defaulting to `default_branch`, a lazy namespace cache and a
  `requests.Session`;
- the class attributes `BASE_URL`, `default_branch`, `_FORK_HOSTS`,
  `_WRITE_RETRIES`, `_WRITE_BACKOFF`;
- the namespace resolution from the API profile (`GET /user`);
- the lifecycle methods (`ensure_repo_exists`, `create_repo`, `fork_repo`,
  `delete_repo`, `wait_ready`), the low-level `_request`, the fork-source
  parser `_split_fork`, the blob-sha lookup `_existing_sha`, and the two
  platform hooks:

- `_write_file` — the create/update strategy: Gitee/GitCode split
  POST (missing) / PUT (exists, sha required), GitHub always PUTs;
- `_is_fork_race` — which transient errors `push` retries (e.g. Gitee
  HTTP 400 "文件新建失败", GitHub 409/422).

Platform-specific token attachment is an implementation detail of
`_request` (query parameter on Gitee/GitCode vs `Authorization: Bearer` on
GitHub); repo-creation extras (e.g. Gitee's `can_comment`) and the
defensive fork rename (Gitee/GitCode) live inside the platform's
`create_repo` / `fork_repo`.

## Gitee Platform Module

> Source: [gitee.py](../../../src/mycelium/interface/sower/gitee.py)

`GiteeClient` is the reference implementation for Gitee repositories
(Gitee API v5). It is bound to exactly one target, selected by two
**mutually exclusive** constructor arguments:

- **`repo` mode** — manage `<namespace>/repo`: create it when missing, then
  push into it;
- **`fork` mode** — disguise mode: fork a *Gitee* source repository into
  this account under the **same name** (the Gitee fork API does not support
  custom names). If a same-named repository already exists in the account
  (e.g. from an earlier fork), it is reused instead of forking again.

The personal space `namespace` is resolved automatically from the
authorized user's profile (`GET /user`) on first use and cached — there is
**no `owner` parameter**, so a mistyped owner is impossible.

Cross-platform sources (GitHub, GitLab, ...) are **not supported yet**: the
Gitee OpenAPI v5 has no import/clone endpoint, so such fork links are
rejected with a hint to import the repository manually on the Gitee web UI.

> **To avoid polluting the open-source community, never send pull requests
> to upstream repositories** — a forked copy is a disguise container, not a
> contribution.

- **Push** — `push(path, data, commit_message=...)` creates or updates a
  file through the contents API: POST to create (no sha), PUT to update
  (current blob sha required).

The access token is never embedded in the module; it is always passed
explicitly as the `access_token` constructor argument.

**Access-token permissions.** Create the token at
[gitee.com/personal_access_tokens](https://gitee.com/personal_access_tokens)
(Settings → Security → personal access tokens). Whether you pick a
personal or a repo-level token, Mycelium needs only two scopes:
`user_info` (resolving the namespace) and `projects` (repository
read/write). The form offers two broad categories (single choice):

| Type             | Scope                                                                             |
| ---------------- | --------------------------------------------------------------------------------- |
| Personal token   | Access to **all resources** within the account's authorized scope                 |
| Repo-level token | Effective **only for the specified repository** — more converged, **recommended** |

Tick only these two (the parenthesized notes below are ours, not from the UI):

- ✅ `user_info` — access your personal info and recent activity (required, auto-checked)
- ✅ `projects` — view, create, update your projects (required by Mycelium)

Never store tokens in the repository: every module takes the token only as
a runtime argument (constructor / argv). Sower signing keys live in
gitignored `*.key` PKCS#8 PEM files (`mycelium.crypto` `save`/`load`,
optionally encrypted via `MYCELIUM_KEY_PASSPHRASE`); the demo/legacy raw
files (`examples/feed.dat`, `examples/publisher.dat`, `examples/config.dat`)
are gitignored by explicit path. `examples/ChangeLog.dat` is the one
tracked exception — it is a committed example feed.

**The only local exception**: `tests/interface/tokens.py` is a gitignored,
never-committed local file where you can drop your own throwaway test
tokens for the `tests/interface/live_*.py` smoke tests — tokens therefore
never enter the repository. Never put real user tokens there; the live
tests still prefer an explicit `argv` token and only fall back to that
file when none is given.

## GitCode Platform Module

> Source: [gitcode.py](../../../src/mycelium/interface/sower/gitcode.py)

GitCode and AtomGit are the **same platform** under two names: the API is
identical on both domains. `GitCodeClient` uses `gitcode.com` by default
and accepts `atomgit.com` as an alias (via the `host` argument or in fork
source URLs). Its feature set mirrors `GiteeClient`:

- **`repo` mode** — manage `<namespace>/repo`: create it when missing, then
  push into it;
- **`fork` mode** — disguise mode: fork a *GitCode* source repository into
  this account under the **same name**, reusing an existing same-named
  repository if present;
- the personal space `namespace` is resolved from `GET /user` — no `owner`
  parameter;
- cross-platform sources (GitHub, Gitee, ...) are **not supported yet** —
  such fork links are rejected with a hint to import manually on the
  GitCode web UI.

Platform quirks: the GitCode contents API replies **HTTP 404** for a
missing file (Gitee returns an empty list instead), and the default branch
is `main`.

> **To avoid polluting the open-source community, never send pull requests
> to upstream repositories** — a forked copy is a disguise container, not a
> contribution.

**Access-token permissions.** Create the token at
[gitcode.com/setting/token-classic](https://gitcode.com/setting/token-classic).
Every second- and third-level option has three choices — **read/write /
read-only / forbidden**. Set **everything to forbidden except the items
marked below** (the indentation in the UI does **not** imply parent-child
relations — configure each row independently):

<table>
  <thead>
    <tr><th>Level</th><th>Permission</th><th>Meaning</th><th>Recommended</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>User</td>
      <td>Access your personal info and recent activity</td>
      <td>Your profile and recent activity</td>
      <td><strong>🟡 read-only</strong></td>
    </tr>
    <tr>
      <td rowspan="2">Project</td>
      <td>View, create, update your projects</td>
      <td>Project read/write</td>
      <td><strong>🟢 read/write</strong></td>
    </tr>
    <tr>
      <td>Repository</td>
      <td>Bash client upload/download (the logical conflict point)</td>
      <td><strong>🟢 read/write</strong></td>
    </tr>
  </tbody>
</table>

## GitHub Platform Module

> Source: [github.py](../../../src/mycelium/interface/sower/github.py)

`GithubClient` mirrors `GiteeClient` for GitHub repositories (REST API).
Two platform-specific differences:

- **Authentication** — GitHub takes the token via the `Authorization:
  Bearer` header, not an `access_token` query parameter (Gitee/GitCode use
  the latter);
- **Contents API** — GitHub uses a **single PUT** endpoint for both create
  and update (the current blob sha is included only when the file already
  exists), where Gitee splits POST/PUT.

Its feature set otherwise matches `GiteeClient`:

- **`repo` mode** — manage `<login>/repo`: create it when missing, then
  push into it;
- **`fork` mode** — disguise mode: fork a *GitHub* source repository into
  this account under the **same name**, reusing an existing same-named
  repository if present;
- the account login (`namespace`) is resolved from `GET /user` — no `owner`
  parameter;
- cross-platform sources (Gitee, GitCode, ...) are **not supported yet** —
  such fork links are rejected with a hint to import manually on the
  GitHub web UI.

Platform quirks: GitHub's contents API replies **HTTP 404** for a missing
file, and a fork materializes asynchronously — a write issued right after
forking can transiently fail (409/422) and is retried briefly.

> **To avoid polluting the open-source community, never send pull requests
> to upstream repositories** — a forked copy is a disguise container, not a
> contribution.

**Access-token permissions.** Create a **fine-grained** personal access
token at
[github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new)
(Fine-grained token): **Repository access → All repositories**, then in
**Permissions** search for and add the two below, both set to **Read and
write** — `Metadata` is mandatory and is already in the list automatically
(read-only):

| Permission     | Why                                                                                    |
| -------------- | -------------------------------------------------------------------------------------- |
| Administration | Create / delete the repository (repo mode, fork mode and test cleanup)                 |
| Contents       | Create and update the feed file through the contents API                               |

**CDN acceleration.** Subscribers fetch the feed blob from the spore host,
which by default is `raw.githubusercontent.com` — reachable but sometimes
slow or blocked in some regions. The `cdn` constructor argument accepts a
`bool` or a callable that rewrites a raw `githubusercontent.com` URL into
an accelerated mirror: `True` selects the **jsDelivr** mirror
(`cdn.jsdelivr.net/gh/...`), a callable is used as-is, and `False` (the
default) keeps raw links:

```python
client = GithubClient(token, repo="my-feed-repo")              # raw by default (no CDN)
link = client.spore_link("feed.dat", cfg.vk)                   # raw.githubusercontent.com host
client = GithubClient(token, repo="my-feed-repo", cdn=True)    # jsDelivr mirror
client = GithubClient(token, repo="my-feed-repo", cdn=custom)  # custom mirror callable
```

Note that jsDelivr serves **public** repositories only: for a private
repository keep the default `cdn=False` (the picker then needs an
authenticated session for the raw host).

## Adding a Platform

For another git-hosting platform, subclass `GitPlatformClient` in a sibling
module of `gitee.py` (e.g. `gitlab.py`) and implement the full contract
(the constructor, the class attributes and every abstract method listed
above); for a non-git backend (e.g. a plain WebDAV server), subclass
`Storage` directly and implement `push`. Export the client from
`sower/__init__.py` alongside the others, and it becomes usable by the
same sower workflow.
