# Gitee Platform Module

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
