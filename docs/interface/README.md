# Interface Module

The role-based entry layer of Mycelium: it splits the system into two
clearly separated sides — **sower** and **picker** — and is the
only place that talks to the outside world (hosting platforms, network).

## Roles

- **Sower** (`mycelium.interface.sower`) — owns the crypto
  configuration and pushes the encrypted feed blob into a hosting backend.
  Pushing is its only storage primitive; it never pulls. In ecosystem
  terms it cultivates the sclerotium in the soil and sheds spores (hands
  out the links).
- **Picker** (`mycelium.interface.picker`) — holds only a spore
  link (host/path/verification key) and pulls the feed, then decrypts and
  verifies it with the key embedded in the link. In ecosystem terms it
  catches a spore, follows its trail back to the sclerotium and harvests
  the fruit.

The two sides meet nowhere in code: a sower that wants to read back
its own feed does so by calling the picker interface.

## Package Layout

```text
interface/
    __init__.py     # top-level exports: Storage, GitPlatformClient, GiteeClient, GitCodeClient, GithubClient, Hypha
    sower/          # sower side
        base.py     # Storage — push-only contract; GitPlatformClient — abstract git-hosting contract
        gitee.py    # Gitee platform module: GiteeClient (reference impl.)
        gitcode.py  # GitCode/AtomGit platform module: GitCodeClient
        github.py   # GitHub platform module: GithubClient
    picker/         # picker side
        hypha.py    # Hypha — pull a spore link into a verified sclerotium
```

## Quick Start

Sower (the `wire` bytes come from `Sclerotium.encrypt(cfg)`, see
`mycelium.protocol`):

```python
from mycelium.interface.sower import GiteeClient, GitCodeClient, GithubClient

# The personal space (namespace) is resolved from the API profile
# (GET /user) — there is no owner parameter.
client = GiteeClient(access_token, repo="my-feed-repo")
client.ensure_repo_exists()                # create when missing
client.push("feed.dat", wire, commit_message="publish demo feed")

# Same workflow on GitCode (or AtomGit via host="atomgit.com").
client = GitCodeClient(access_token, repo="my-feed-repo")
client.ensure_repo_exists()
client.push("feed.dat", wire, commit_message="publish demo feed")

# Same workflow on GitHub — raw links by default; pass cdn=True for the
# jsDelivr mirror, or a custom callable for another mirror.
client = GithubClient(access_token, repo="my-feed-repo")
client.ensure_repo_exists()
client.push("feed.dat", wire, commit_message="publish demo feed")
link = client.spore_link("feed.dat", cfg.vk)  # picker link
```

Picker:

```python
from mycelium.interface.picker import Hypha

sclerotium = Hypha().pull("mycelium://...")
```

## Adding a New Platform

To publish to another git-hosting platform (GitLab, ...), add a sibling
module to `sower/gitee.py` that subclasses
`sower.base.GitPlatformClient` and implements the full abstract
contract; for a non-git backend (e.g. a WebDAV server) subclass
`sower.base.Storage` and implement `push(path, data)`. The picker
side needs no change: `Hypha` fetches through plain HTTPS URLs from the
spore link, so any HTTP-reachable host works.
