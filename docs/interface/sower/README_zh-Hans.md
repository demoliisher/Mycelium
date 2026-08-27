# 播种者接口 Sower

Mycelium 的播种者：把加密后的订阅源文件推入托管后端，供采摘者拉取。

## 存储契约 Storage Contract

> 源码：[base.py](../../../src/mycelium/interface/sower/base.py)

`Storage` 是各平台共享的**仅推送**抽象契约。这里刻意没有 `pull`：取回是采摘者的行为（见 `mycelium.interface.picker`），播种者想读回自己发布的内容，就应自行调用采摘者接口。

```python
from abc import ABC, abstractmethod

class Storage(ABC):
    @abstractmethod
    def push(self, path: str, data: bytes) -> None:
        """创建或覆盖 ``path`` 为 ``data``。"""
        pass
```

## GitPlatformClient 契约 GitPlatformClient Contract

> 源码：[base.py](../../../src/mycelium/interface/sower/base.py)

`GitPlatformClient(Storage)` 是各 git 托管平台客户端共享的抽象契约。与 `Storage` 一样，它是纯契约：下面每个方法都是 `pass` 占位，且刻意**不**重定义 `push`——`push` 保持为 `Storage` 的抽象方法，因此本类仍是抽象基类（无法实例化）。各平台模块自行实现完整生命周期，平台客户端因此自包含。客户端必须提供：

- 构造函数：`access_token` 外加 `repo` / `fork` 中**恰好一个**（互斥；fork 模式以源仓库名为目标）、默认取 `default_branch` 的 `branch`、惰性命名空间缓存与 `requests.Session`；
- 类属性 `BASE_URL`、`default_branch`、`_FORK_HOSTS`、`_WRITE_RETRIES`、`_WRITE_BACKOFF`；
- 从 API 资料（`GET /user`）解析命名空间；
- 生命周期方法（`ensure_repo_exists`、`create_repo`、`fork_repo`、`delete_repo`、`wait_ready`）、低层 `_request`、fork 源解析 `_split_fork`、blob sha 查询 `_existing_sha`，以及两个平台钩子：

- `_write_file` — 创建/更新策略：Gitee/GitCode 拆分 POST（缺失）/ PUT（已存在，需 sha），GitHub 一律 PUT；CNB **没有** contents 写入 API——它的 `_write_file` 直接抛错，`push` 用真实的 `git push` 写入；
- `_is_fork_race` — `push` 重试哪些瞬时错误（如 Gitee HTTP 400「文件新建失败」、GitHub 409/422）。

令牌的附加方式是 `_request` 的实现细节（Gitee/GitCode 用查询参数，GitHub 用 `Authorization: Bearer`）；建仓请求体的额外字段（如 Gitee 的 `can_comment`）与复刻的防御性改名（Gitee/GitCode）则在平台自身的 `create_repo` / `fork_repo` 内部实现。

## Gitee 平台模块 Gitee Platform Module

> 源码：[gitee.py](../../../src/mycelium/interface/sower/gitee.py)

`GiteeClient` 是针对 Gitee 仓库（Gitee API v5）的参考实现，绑定**恰好一个**目标，由两个**互斥**的构造参数选定：

- **`repo` 模式** — 管理 `<namespace>/repo`：缺失时创建，然后向其中推送；
- **`fork` 模式** — 伪装模式：把 *Gitee* 源仓库复刻进本账户，**保留同名**（Gitee 复刻 API 不支持自定义名称）。若账户中已存在同名仓库（例如之前复刻过），则直接复用，不再重复复刻。

个人空间 `namespace`（个人空间地址）由授权用户资料（`GET /user`）在首次使用时自动解析并缓存——**没有 `owner` 参数**，因此不可能输错属主。

**暂不支持其他平台**（GitHub、GitLab……）：Gitee OpenAPI v5 没有导入/clone 接口，这类 fork 链接会被拒绝，并提示到 Gitee 网页手动导入。

> **为避免污染开源社区，请勿向上游仓库提交 PR**——复刻副本是伪装容器，不是贡献。

- **推送** — `push(path, data, commit_message=...)` 通过 contents API 创建或更新文件：POST 创建（无需 sha），PUT 更新（需当前 blob sha）。

访问令牌从不写死在模块里，始终通过构造参数 `access_token` 显式传入。

**令牌权限配置。** 在 [gitee.com/personal_access_tokens](https://gitee.com/personal_access_tokens)（设置→安全设置→私人令牌）
的「＋生成新令牌」表单创建。**无论选私人令牌还是仓库级私人令牌，Mycelium 都只需要两个权限**：`user_info`（解析个人空间）与 `projects`（仓库读写）。表单分**两个大类（单选）**：

| 类型           | 生效范围                                       |
| -------------- | ---------------------------------------------- |
| 私人令牌       | 可访问账号下**授权范围内的全部资源**           |
| 仓库级私人令牌 | **仅对指定仓库范围生效**，权限更收敛——**推荐** |

只勾选以下两项（括号内为本文档补充的说明，并非界面自带）：

- ✅ `user_info` 访问你的个人信息、最新动态等（已自动勾选的必选权限，无需手动勾选）
- ✅ `projects` 查看、创建、更新你的项目（Mycelium 必须权限）

切勿把令牌存进仓库：所有模块都只通过运行时参数（构造函数 / argv）接收令牌。播种者签名私钥存放于被 gitignore 的 `*.key` PEM 文件（`mycelium.crypto` 的 `save`/`load`，可选用 `MYCELIUM_KEY_PASSPHRASE` 加密）；旧式裸字节私钥文件 `*.dat` 与 `priv_*.py` 同样被 gitignore。

**唯一的本地例外**：`tests/interface/tokens.py` 是**被 gitignore、永不入库**的本地文件，可放入你自己的**一次性测试令牌**供 `tests/interface/live_*.py` 冒烟测试使用——令牌因此始终不会进入仓库。其中绝不放真实用户令牌；live 测试仍优先接受 argv 显式传入的令牌，仅在缺省时回退到该文件。

## GitCode 平台模块 GitCode Platform Module

> 源码：[gitcode.py](../../../src/mycelium/interface/sower/gitcode.py)

GitCode 与 AtomGit 是**同一个平台的两个名字**：两个域名上的 API 完全一致。
`GitCodeClient` 默认使用 `gitcode.com`，也接受 `atomgit.com` 作为别名（通过 `host` 参数或 fork 源链接）。功能规模与 `GiteeClient` 对齐：

- **`repo` 模式** — 管理 `<namespace>/repo`：缺失时创建，然后向其中推送；
- **`fork` 模式** — 伪装模式：把 *GitCode* 源仓库复刻进本账户，**保留同名**；账户中已存在同名仓库时直接复用；
- 个人空间 `namespace` 由 `GET /user` 解析——**没有 `owner` 参数**；
- **暂不支持其他平台**（GitHub、Gitee……）——这类 fork 链接会被拒绝，并提示到 GitCode 网页手动导入。

平台差异：GitCode 的 contents API 对缺失文件返回 **HTTP 404**（Gitee 返回空列表），默认分支为 `main`。

> **为避免污染开源社区，请勿向上游仓库提交 PR**——复刻副本是伪装容器，不是贡献。

**令牌权限配置。** 在「访问令牌（经典）」页面创建：

```text
https://gitcode.com/setting/token-classic
```

点击「+新建访问令牌」→「配置访问令牌的权限范围」。每个二、三级选项都有**读写 / 只读 / 禁止**三档选择；除下表标注的建议配置外，**其余全部设为「禁止」**（后台缩进不代表父子级关联——按行独立配置）：

<table>
  <thead>
    <tr><th>层级</th><th>权限项</th><th>说明</th><th>建议</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>用户</td>
      <td>访问你的个人信息、最新动态等</td>
      <td>个人资料与动态</td>
      <td><strong>🟡 只读</strong></td>
    </tr>
    <tr>
      <td rowspan="2">项目</td>
      <td>查看、创建、更新你的项目</td>
      <td>项目读写</td>
      <td><strong>🟢 读写</strong></td>
    </tr>
    <tr>
      <td>Repository</td>
      <td>bash 客户端的上传下载（逻辑冲突所在）</td>
      <td><strong>🟢 读写</strong></td>
    </tr>
  </tbody>
</table>

## GitHub 平台模块 GitHub Platform Module

> 源码：[github.py](../../../src/mycelium/interface/sower/github.py)

`GithubClient` 为 GitHub 仓库（REST API）复刻了 `GiteeClient`。两个平台差异：

- **认证方式** — GitHub 通过 `Authorization: Bearer` 请求头携带令牌，而非 `access_token` 查询参数（Gitee/GitCode 用后者）；
- **contents API** — GitHub 创建与更新**统一用 PUT**（文件已存在时才附带当前 blob sha），Gitee 则拆成 POST/PUT 两个端点。

其余功能与 `GiteeClient` 对齐：

- **`repo` 模式** — 管理 `<login>/repo`：缺失时创建，然后向其中推送；
- **`fork` 模式** — 伪装模式：把 *GitHub* 源仓库复刻进本账户，**保留同名**；账户中已存在同名仓库时直接复用；
- 账户登录名（`namespace`）由 `GET /user` 解析——**没有 `owner` 参数**；
- **暂不支持其他平台**（Gitee、GitCode……）——这类 fork 链接会被拒绝，并提示到 GitHub 网页手动导入。

平台差异：GitHub 的 contents API 对缺失文件返回 **HTTP 404**；fork 是异步落地的——复刻后立即写入可能短暂报 409/422，`push` 会短暂重试。

> **为避免污染开源社区，请勿向上游仓库提交 PR**——复刻副本是伪装容器，不是贡献。

**令牌权限配置。** 创建 **fine-grained（细粒度）** 个人访问令牌：
[github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new)。
**Repository access 选择 All repositories**；在 **Permissions** 中搜索并添加以下两项，均设为 **Read and write**——`Metadata` 为必选项且已自动加入权限列表（只读）：

| 权限           | 用途                                              |
| -------------- | ------------------------------------------------- |
| Administration | 创建 / 删除仓库（repo 模式、fork 模式与测试清理） |
| Contents       | 通过 contents API 创建与更新订阅源文件            |

**CDN 加速。** 采摘者从孢子 host 拉取订阅源文件，默认是 `raw.githubusercontent.com`——可达，但部分地区访问缓慢或被阻断。`cdn` 构造参数接收 `bool` 或可调用对象，把 raw `githubusercontent.com` 链接改写成加速镜像：`True` 选用默认的 **jsDelivr** 镜像（`cdn.jsdelivr.net/gh/...`），传入自定义函数则原样使用，`False`（默认值）保留 raw 链接：

```python
client = GithubClient(token, repo="my-feed-repo")              # 默认保留 raw（不加速）
link = client.spore_link("feed.dat", cfg.vk)                   # host 为 raw.githubusercontent.com
client = GithubClient(token, repo="my-feed-repo", cdn=True)    # jsDelivr 镜像
client = GithubClient(token, repo="my-feed-repo", cdn=custom)  # 自定义镜像函数
```

注意 jsDelivr 只加速**公开**仓库：私有仓库保持默认 `cdn=False`（采摘者需用带认证的会话访问 raw host）。

## CNB 平台模块 CNB Platform Module

> 源码：[cnb.py](../../../src/mycelium/interface/sower/cnb.py)

CNB（cnb.cool）是腾讯云的云原生代码托管平台。`CnbClient` 为 CNB 仓库复刻了 `GiteeClient`，有三个平台性差异：

- **仓库只能存在于「组织」下**（组织）。CNB 没有个人仓库概念，因此构造函数需要传入组织路径（`group`），缺失时自动创建；`group` 也可省略——此时按资料用户名解析组织：username 同名组织已存在则使用；否则复用已有**空组织**（尚无仓库的组织；组织列表来自 `GET /user/groups`，需要 `account-engage` 权限，缺该权限则跳过搜索）；否则自动创建 username 同名组织。`namespace` 因此是组织路径而非资料登录名——这是对共享契约的唯一偏离（其他平台都从 `GET /user` 解析命名空间；首次使用仍会调用资料接口以尽早校验令牌、并在省略 `group` 时取得用户名）。
- **没有 contents 写入 API** —— `push` 用真实的 `git push` 写入：模块把仓库克隆到临时目录，覆写文件后提交并推送（用户名为 `cnb`，访问令牌作密码，经临时凭据存储文件交给 git，用完即删）。契约钩子 `_write_file` 在 CNB 上没有对应的 HTTP 端点，直接抛错。
- **没有 fork API** —— `fork` 模式仍可传入（目标名与其他平台一样解析），但**一旦使用必然抛错**，并提示到 CNB 网页手动 fork。

其余功能与 `GiteeClient` 对齐：

- **`repo` 模式** — 管理 `<group>/repo`：缺失时创建（组织缺失则一并创建）并推送；省略 `group` 时组织按资料用户名解析（见上）；
- 创建时设置仓库名与可见性（`visibility`：`public` / `private` / `secret`）；
- 写入订阅源仓库 git 历史的提交身份可用 `git_author`（`"Name <email>"`）配置，默认为中性的 `Mycelium Sower <sower@mycelium.local>`——请选择无法与你其他平台身份关联的身份。

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

另请注意：OpenAPI 会拒绝删除根组织下的仓库/组织（HTTP 412「root group management rules」）——`delete_repo` 会如实抛出该拒绝，必要时清理需在 CNB 网页上进行。

> **为避免污染开源社区，请勿向上游仓库提交 PR**——复刻副本是伪装容器，不是贡献。

**令牌权限配置。** 在 [cnb.cool/profile/token](https://cnb.cool/profile/token)（个人设置 → 访问令牌）创建。**资源范围选「全部」**，**常见场景不选**；然后在**授权范围**中只勾选下表所列项（其余保持平台默认：公开仓库默认只读、私有默认无权限）：

| 授权范围                | Mycelium 的用途                                                                         |
| ----------------------- | --------------------------------------------------------------------------------------- |
| 只读 `account-profile`  | 解析/校验授权用户（`GET /user`，命名空间校验）                                          |
| 只读 `account-engage`   | 列出授权用户的组织（`GET /user/groups`）——省略 `group` 时复用空组织                     |
| 读写 `repo-code`        | 读取代码/分支/commit 与 **git push**（Git 客户端凭据）——写入路径                        |
| 读写 `repo-delete`      | 删除仓库（live 测试清理；对根组织常被平台拒绝）                                         |
| 读写 `group-manage`     | 组织缺失时自动创建组织                                                                  |
| 读写 `group-resource`   | 在组织下创建仓库                                                                        |
| 只读 `repo-basic-info`  | 仓库信息读取（live 测试）                                                               |
| 读写 `group-delete`     | 删除组织（live 测试清理）                                                               |

注意：CNB 对根组织的创建有年度配额——若自动创建报 HTTP 429，请先在网页创建一次组织，再把其路径作为 `group` 传入（省略 `group` 时模块会优先复用已有的空组织，仅在无可用组织时才新建）。

## 添加平台 Adding a Platform

对于另一个 git 托管平台，在 `gitee.py` 旁新增同级模块（如 `gitlab.py`），继承 `GitPlatformClient` 并实现完整契约（构造函数、类属性与上面列出的每个抽象方法）；
对于非 git 后端（如普通 WebDAV 服务器），直接继承 `Storage` 并实现 `push`。
在 `sower/__init__.py` 中与其他客户端一起导出，即可接入同一套播种工作流。
