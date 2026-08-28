# Git Push Backend

> Source: [git.py](../../../src/mycelium/interface/sower/git.py)

`GitPusher` is a minimal pure-Python single-file git push over the git
smart HTTP protocol, built on [dulwich](https://github.com/jelmer/dulwich)
— **no `git` executable is required**. Platform modules whose only write
path is a real git push (CNB has no contents write API) use it instead of
shelling out to the system `git`, which removes an entire class of user
environment problems:

- the user does not need a `git` client installed or on `PATH`;
- the commit identity is written directly into the commit object by the
  caller (resolved from the platform API), so there is no `git config
  user.name/email` to set — and no credential helper, Git Credential
  Manager popup, or terminal prompt to suppress;
- the push runs entirely in memory: no clone, no working tree, no
  temporary credential store file.

## API

```python
pusher = GitPusher("https://cnb.cool/mycelium/my-feed", "cnb", token)
head = pusher.head("main")              # the remote tip (hex sha) or None
result = pusher.push_file(
    "main", "feed.dat", b"...", "Create file feed.dat",
    "Rainbow", "rainbow@example.com",   # author == committer, verbatim
)
# -> {"commit": {"sha": "..."}, "message": "Create file feed.dat"}
```

`push_file` builds the objects in memory — a blob with the file bytes, a
tree carrying the path (nested paths become nested trees), a commit with
the given author/committer identity — parents the commit on the current
remote tip of the branch (a fresh repository gets a root commit, which also
removes the transient "branch still initializing" race), and uploads the
objects with `client.send_pack`, fast-forwarding `refs/heads/<branch>`.

The `url` is resolved by `dulwich.client.get_transport_and_path`, so a
local filesystem path or `file://` URL works too — the unit tests
(`tests/interface/test_git.py`) exercise a real push against a local bare
repository with no network.

## Errors

dulwich raises its own exceptions; `GIT_ERRORS` is the tuple of the ones a
push can raise (protocol errors, `NotGitRepository`, 401/407
authentication), which platform `push` methods catch around the git write.
`is_transient_git_error(exc)` tells a caller whether the failure looks like
the transient fresh-repository race or a network hiccup (worth retrying)
versus an authentication failure or a rejected pack (not worth retrying).

## Backup mode

`GitPlatformClient` (see [base.py](README.md)) has an optional
git-push backup mode: platforms whose normal write path is the contents
API (Gitee, GitCode, GitHub) can override `_git_identity` and `_git_remote`
to resolve a commit identity from the platform API and the git credentials
for the target repository; when the contents API write fails after the
transient-race retries, `push` falls back to `GitPusher`. When no identity
can be resolved the original API error is re-raised instead.
