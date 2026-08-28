# GitCode Platform Module

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
is `main`. When the contents write fails after the transient-race retries,
`push` falls back to a **real git push** through the pure-Python
[git push backend](git.md) (`GitPusher`) — the commit identity comes from
the GitCode profile (login + profile email) and the git credentials are
the login with the access token as the password; if no identity is
resolvable the original API error is re-raised.

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
