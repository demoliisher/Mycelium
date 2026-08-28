# CNB Platform Module

> Source: [cnb.py](../../../src/mycelium/interface/sower/cnb.py)

CNB (cnb.cool) is Tencent Cloud's cloud-native code-hosting platform.
`CnbClient` mirrors `GiteeClient` for CNB repositories, with three
platform-shaped differences:

- **Repositories live inside organizations** (组织). CNB has no personal
  repository concept, so the constructor takes the organization path
  (`group`) and creates it when missing. `group` is optional — when
  omitted, the organization is resolved from the profile username: the
  username-named organization when it already exists, else an existing
  organization with no repositories yet (reused instead of creating a new
  one; the organization list comes from `GET /user/groups`, which needs
  the `account-engage` scope — without it the search is skipped), else a
  username-named organization is auto-created. The `namespace` therefore
  is the organization path, not the profile login — the one deviation from
  the shared contract, which resolves the namespace from `GET /user`
  everywhere else (the profile call still runs on first use to validate
  the token and, without `group`, to learn the username).
- **No contents write API** — `push` writes with a real `git push`: the
  module clones the repository into a temporary directory, overwrites the
  file, commits and pushes (username `cnb`, the access token as the
  password, handed to git through a temporary credential store that is
  deleted right after). The `_write_file` contract hook has no HTTP
  counterpart on CNB and raises.
- **No fork API** — `fork` mode is accepted (the target name is parsed like
  on the other platforms) but **always raises** when used, with a hint to
  fork the repository manually on the CNB web UI.

Its feature set otherwise matches `GiteeClient`:

- **`repo` mode** — manage `<group>/repo`: create it (and the organization
  when missing) and push into it; without `group` the organization is
  resolved from the profile username (see above);
- the target repository name and visibility are set on creation
  (`visibility`: `public` / `private` / `secret`);
- the commit identity written into the feed repository's git history comes
  from the platform API — the profile username (`GET /user`) with the
  platform's git commit email (`GET /user/emails`, which needs the
  `account-email:r` scope; without that scope the profile email from
  `GET /user` is used). If no username or email can be resolved the push
  fails — there is no fallback identity and no identity parameter.

Platform quirks: the API authenticates with an `Authorization: Bearer`
header (like GitHub); a missing file is **HTTP 404** while an empty
repository answers the contents endpoint with `type: "empty"`; the default
branch is `main`; and the raw content endpoint requires the token **even
for public repositories**, so CNB spore links always need an authenticated
picker session:

```python
client = CnbClient(token, repo="my-feed-repo", group="mycelium",
                   visibility="private")
# group is optional: without it the organization is resolved from the
# profile username (username-named org, an existing empty org, or a new one).
link = client.spore_link("feed.dat", cfg.vk)   # host: api.cnb.cool

# The picker must attach the token (the raw endpoint requires it).
class TokenSession(requests.Session):
    def get(self, url, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        headers["Authorization"] = f"Bearer {token}"
        return super().get(url, headers=headers, **kwargs)

Hypha(session=TokenSession()).pull(link)
```

Deletion: by default the OpenAPI refuses to delete repositories inside
root organizations (HTTP 412, "root group management rules"). Enable the
web-only setting 允许通过 Open API 删除组织下资源 in the organization's
settings (组织设置 → 管控 → 组织管控 → 危险操作) and `delete_repo` works —
on a 412 `delete_repo` raises a `ValueError` carrying this guidance. The
organization itself can only be deleted once it is empty (all
repositories/sub-organizations removed), and deleting organizations does
not free the yearly root-organization creation quota (HTTP 429) — treat
root organizations as a scarce yearly resource: **do not delete them
unless necessary**, deletion is permanent quota loss. The official
OpenAPI spec (<https://api.cnb.cool/swagger.json>) confirms this design:
`root_group_protection` appears only in the `GET /{slug}/-/settings`
response (the `PUT` body omits it — web-only), sub-organizations are
read-only (`GET /user/groups/{slug}`, `GET /{slug}/-/sub-groups`; no
create endpoint, so the yearly root-org quota cannot be bypassed),
`POST /{repo}/-/git/blobs` is the only git write endpoint (no
tree/commit/ref writes — a real git push is the only write path), and
the `x-cnb-identity-ticket` header (a WeChat auth ticket returned on the
first attempt) gates every dangerous DELETE (repository, organization,
mission, registry).

> **To avoid polluting the open-source community, never send pull requests
> to upstream repositories** — a forked copy is a disguise container, not a
> contribution.

**Access-token permissions.** Create the token at
[cnb.cool/profile/token](https://cnb.cool/profile/token) (个人设置 → 访问令牌).
Set **资源范围 (resource scope) to 全部 (all)** and leave **常见场景
(common scenarios) unselected**; then tick only the following
**授权范围 (authorization scopes)** (everything else keeps the platform
default: public repositories read-only, private ones without permission):

| Scope                        | Why Mycelium needs it                                                                                                                                                  |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 只读 `account-profile`       | Resolve/validate the authorized user (`GET /user`, the namespace check; also the commit identity's profile email)                                                      |
| 只读 `account-email`         | The authorized user's git commit email (`GET /user/emails`) — the commit identity; falls back to the profile email when the scope is missing, otherwise the push fails |
| 只读 `account-engage`        | List the authorized user's organizations (`GET /user/groups`) — the empty-org reuse when `group` is omitted                                                            |
| 读写 `repo-code`             | Read code/branches/commits and the **git push** (Git client credentials) — the write path                                                                              |
| 读写 `repo-delete`           | Delete repositories (live-test cleanup; often refused for root orgs)                                                                                                   |
| 读写 `group-manage`          | Auto-create the organization when it does not exist yet                                                                                                                |
| 读写 `group-resource`        | Create repositories inside the organization                                                                                                                            |
| 只读 `repo-basic-info`       | Repository info reads (live tests)                                                                                                                                     |
| 读写 `group-delete`          | Delete the organization (live-test cleanup)                                                                                                                            |

Note: CNB limits root-organization creation to a yearly quota that applies
to the web UI and the API alike (creating via the web UI also returns
HTTP 429 once exhausted, and deleting organizations does not free it) —
if auto-creation fails with HTTP 429, the organization has to be created
when the quota allows or by the platform admin, and its path passed as
`group` (when `group` is omitted the module reuses an existing
organization without repositories first, so a new one is only created
when nothing is available).

## CNB References

CNB is a niche platform with scattered docs; the following official
sources help contributors (human or AI) verify API behavior:

- Official OpenAPI spec: <https://api.cnb.cool/swagger.json> — endpoint
  list, permission scopes and request/response schemas
- Official Skills / cnb-cli source: <https://cnb.cool/cnb/skills/cnb-skill>
  — the generated OpenAPI client (MIT), a handy reference for endpoint
  shapes and payloads
- Platform docs: <https://docs.cnb.cool/>
