# Sower Interface

The sower side of Mycelium: push the encrypted feed blob into a
hosting backend so pickers can pull it.

## Platform modules

Each supported platform has its own document:

- [Gitee](gitee.md) — `GiteeClient` (Gitee API v5)
- [GitCode](gitcode.md) — `GitCodeClient` (AtomGit alias)
- [GitHub](github.md) — `GithubClient`
- [CNB](cnb.md) — `CnbClient` (real `git push`; the commit identity comes
  from the platform API)

The git write backend behind CNB's push — and the backup mode of the
contents-API platforms — is the pure-Python [git push backend](git.md)
(`GitPusher`, dulwich-based, no `git` executable required).

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
  POST (missing) / PUT (exists, sha required), GitHub always PUTs; CNB has
  **no contents write API** — its `_write_file` raises and `push` writes
  with a real `git push` (see [git.md](git.md));
- `_is_fork_race` — which transient errors `push` retries (e.g. Gitee
  HTTP 400 "文件新建失败", GitHub 409/422).

Platform-specific token attachment is an implementation detail of
`_request` (query parameter on Gitee/GitCode vs `Authorization: Bearer` on
GitHub); repo-creation extras (e.g. Gitee's `can_comment`) and the
defensive fork rename (Gitee/GitCode) live inside the platform's
`create_repo` / `fork_repo`.

## Git-push backup mode

A platform whose normal write path is the contents API (Gitee, GitCode,
GitHub) can opt into a **backup mode**: when the contents write fails after
the transient-race retries, `push` falls back to a real git push through
`GitPusher` ([git.md](git.md)) instead of raising. To enable it, override
the two hooks from `base.py`:

- `_git_identity()` → `(name, email)` — the commit identity, resolved from
  the platform API (the authorized user's profile; GitHub additionally
  falls back to its anonymous `users.noreply.github.com` mailbox). Return
  `None` when the platform has no backup mode or no identity is resolvable;
- `_git_remote()` → `(url, username, password)` — the HTTPS clone/push URL
  of the target repository and its git credentials (e.g. GitHub uses the
  conventional `x-access-token` username with the token as the password).

`_push_git_backup(file_path, content_bytes, commit_message)` (shared, in
`base.py`) builds the `GitPusher` and pushes; when either hook returns
`None` the original API error is re-raised. CNB always uses the git push
(its only write path), so it needs no backup mode.

## Adding a Platform

For another git-hosting platform, subclass `GitPlatformClient` in a sibling
module of `gitee.py` (e.g. `gitlab.py`) and implement the full contract
(the constructor, the class attributes and every abstract method listed
above). If the platform has no contents write API, implement `push` with a
`GitPusher` like `cnb.py` does; if its contents API may fail in ways the
retry does not cover, consider the backup mode above. For a non-git
backend (e.g. a plain WebDAV server), subclass `Storage` directly and
implement `push`. Export the client from `sower/__init__.py` alongside the
others, and it becomes usable by the same sower workflow. Add a platform
document (`<platform>.md` + optional `<platform>_zh-Hans.md`) next to the
ones above.
