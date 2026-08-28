# GitHub Platform Module

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
forking can transiently fail (409/422) and is retried briefly. When the
contents write fails after the transient-race retries, `push` falls back
to a **real git push** through the pure-Python [git push backend](git.md)
(`GitPusher`) — the commit identity comes from the GitHub profile (the
login with the profile email, else the primary email from `GET
/user/emails`, else GitHub's anonymous `users.noreply.github.com` mailbox)
and the git credentials use the conventional `x-access-token` username
with the token as the password; if no identity is resolvable the original
API error is re-raised.

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
