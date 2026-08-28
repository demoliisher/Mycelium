# CNB 平台模块 CNB Platform Module

> 源码：[cnb.py](../../../src/mycelium/interface/sower/cnb.py)

CNB（cnb.cool）是腾讯云的云原生代码托管平台。`CnbClient` 为 CNB 仓库复刻了 `GiteeClient`，有三个平台性差异：

- **仓库只能存在于「组织」下**（组织）。CNB 没有个人仓库概念，因此构造函数需要传入组织路径（`group`），缺失时自动创建；`group` 也可省略——此时按资料用户名解析组织：username 同名组织已存在则使用；否则复用已有**空组织**（尚无仓库的组织；组织列表来自 `GET /user/groups`，需要 `account-engage` 权限，缺该权限则跳过搜索）；否则自动创建 username 同名组织。`namespace` 因此是组织路径而非资料登录名——这是对共享契约的唯一偏离（其他平台都从 `GET /user` 解析命名空间；首次使用仍会调用资料接口以尽早校验令牌、并在省略 `group` 时取得用户名）。
- **没有 contents 写入 API** —— `push` 用真实的 `git push` 写入：经由纯 Python 的 [git 推送后端](git_zh-Hans.md)（`GitPusher`，基于 dulwich）在内存中构造提交并走 git smart HTTP 协议推送（用户名为 `cnb`，访问令牌作密码）——无需 git 可执行文件、无需 clone、无工作树、无临时凭据存储文件。契约钩子 `_write_file` 在 CNB 上没有对应的 HTTP 端点，直接抛错。
- **没有 fork API** —— `fork` 模式仍可传入（目标名与其他平台一样解析），但**一旦使用必然抛错**，并提示到 CNB 网页手动 fork。

其余功能与 `GiteeClient` 对齐：

- **`repo` 模式** — 管理 `<group>/repo`：缺失时创建（组织缺失则一并创建）并推送；省略 `group` 时组织按资料用户名解析（见上）；
- 创建时设置仓库名与可见性（`visibility`：`public` / `private` / `secret`）；
- 写入订阅源仓库 git 历史的提交身份取自平台 API——`GET /user` 的资料用户名 + `GET /user/emails` 的 git 提交邮箱（需要 `account-email:r` 权限；缺该权限时使用 `GET /user` 的资料邮箱）。用户名或邮箱无法解析时 push 直接失败——没有保底身份，也没有身份参数。

平台差异：API 通过 `Authorization: Bearer` 请求头认证（与 GitHub 相同）；缺失文件返回 **HTTP 404**，而空仓库的 contents 端点返回 `type: "empty"`；默认分支为 `main`；raw 内容端点**即使对公开仓库也要求令牌**，因此 CNB 的孢子链接始终需要带认证的采摘者会话：

```python
client = CnbClient(token, repo="my-feed-repo", group="mycelium",
                   visibility="private")
# group 可省略：不传时按资料用户名解析组织（username 同名组织、已有空组织、或新建）。
link = client.spore_link("feed.dat", cfg.vk)   # host: api.cnb.cool

# 采摘者必须携带令牌（raw 端点要求认证）。
class TokenSession(requests.Session):
    def get(self, url, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        headers["Authorization"] = f"Bearer {token}"
        return super().get(url, headers=headers, **kwargs)

Hypha(session=TokenSession()).pull(link)
```

删除说明：默认情况下 OpenAPI 会拒绝删除根组织下的仓库（HTTP 412「root group management rules」）。在组织设置中开启「允许通过 Open API 删除组织下资源」（组织设置 → 管控 → 组织管控 → 危险操作）后，`delete_repo` 即可删除——该开关仅能在网页修改（API 的设置端点会忽略它）；遇到 412 时 `delete_repo` 会抛出带此指引的 `ValueError`。组织本身需在清空（所有仓库/子组织删除后）才能删除；删除组织不会释放根组织年度创建配额（HTTP 429）——**根组织年度配额宝贵，非必要勿删组织**（删除即永久损失配额）。

官方 OpenAPI（<https://api.cnb.cool/swagger.json>）证实了上述设计：`root_group_protection` 仅存在于 `GET /{slug}/-/settings` 的响应中（`PUT` 请求体不含该字段，故仅网页可改）；子组织只有只读端点（`GET /user/groups/{slug}` 与 `GET /{slug}/-/sub-groups`，无创建端点，根组织年度配额无法绕过）；git 写接口只有 `POST /{repo}/-/git/blobs` 一个（无 tree/commit/ref 写接口，真 git push 是唯一提交途径）；`x-cnb-identity-ticket`（微信身份验证票据，首次请求返回）是仓库、组织、任务集、制品库四类删除操作的通用门槛。

> **为避免污染开源社区，请勿向上游仓库提交 PR**——复刻副本是伪装容器，不是贡献。

**令牌权限配置。** 在 [cnb.cool/profile/token](https://cnb.cool/profile/token)（个人设置 → 访问令牌）创建。**资源范围选「全部」**，**常见场景不选**；然后在**授权范围**中只勾选下表所列项（其余保持平台默认：公开仓库默认只读、私有默认无权限）：

| 授权范围                | Mycelium 的用途                                                                                           |
| ----------------------- | --------------------------------------------------------------------------------------------------------- |
| 只读 `account-profile`  | 解析/校验授权用户（`GET /user`，命名空间校验；也是提交身份的降级邮箱来源）                                |
| 只读 `account-email`    | 读取授权用户的 git 提交邮箱（`GET /user/emails`）——提交身份；缺权限时降级为资料邮箱，两者皆无则 push 失败 |
| 只读 `account-engage`   | 列出授权用户的组织（`GET /user/groups`）——省略 `group` 时复用空组织                                       |
| 读写 `repo-code`        | 读取代码/分支/commit 与 **git push**（Git 客户端凭据）——写入路径                                          |
| 读写 `repo-delete`      | 删除仓库（live 测试清理；对根组织常被平台拒绝）                                                           |
| 读写 `group-manage`     | 组织缺失时自动创建组织                                                                                    |
| 读写 `group-resource`   | 在组织下创建仓库                                                                                          |
| 只读 `repo-basic-info`  | 仓库信息读取（live 测试）                                                                                 |
| 读写 `group-delete`     | 删除组织（live 测试清理）                                                                                 |

注意：CNB 对根组织的创建有年度配额，且**网页与 API 共用该配额**（配额耗尽后网页创建同样返回 HTTP 429，删除组织也不会释放）——若自动创建报 HTTP 429，需等待配额恢复或由平台管理员创建组织，再将其路径作为 `group` 传入（省略 `group` 时模块会优先复用已有的空组织，仅在无可用组织时才新建）。

## CNB 参考资料 CNB References

CNB 是小众平台、资料零散，以下官方来源供贡献者（人类或 AI）核对 API 行为：

- 官方 OpenAPI：<https://api.cnb.cool/swagger.json>——端点清单、权限范围与请求/响应结构
- 官方 Skills / cnb-cli 源码：<https://cnb.cool/cnb/skills/cnb-skill>——生成的 OpenAPI 客户端（MIT），端点形态与载荷的便捷参考
- 平台文档：<https://docs.cnb.cool/>
