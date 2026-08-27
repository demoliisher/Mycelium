# 接口层模块 Interface

Mycelium 的按角色划分的入口层：把系统明确分为**播种者 sower** 与**采摘者 picker** 两侧，也是唯一与外部世界（托管平台、网络）打交道的地方。

## 角色 Roles

- **播种者**（`mycelium.interface.sower`）：持有加密配置，把加密后的订阅源文件推入托管后端。推送是它唯一的存储原语，它从不拉取。生态上：在土壤里栽培菌核、产出并分发孢子（链接）。
- **采摘者**（`mycelium.interface.picker`）：只持有一个孢子链接（host/path/验证公钥），拉取订阅源，并用链接内嵌的公钥解密、验签。生态上：接住孢子，循迹回到菌核，采摘果实（订阅源内容）。

两侧在代码层面互不依赖：播种者想读回自己发布的内容，就去调用采摘者接口。

## 目录结构 Package Layout

```text
interface/
    __init__.py     # 顶层导出：Storage、GitPlatformClient、GiteeClient、GitCodeClient、GithubClient、Hypha
    sower/          # 播种者
        base.py     # Storage —— 仅推送契约；GitPlatformClient —— 抽象的 git 托管契约
        gitee.py    # Gitee 平台模块：GiteeClient（参考实现）
        gitcode.py  # GitCode/AtomGit 平台模块：GitCodeClient
        github.py   # GitHub 平台模块：GithubClient
    picker/         # 采摘者
        hypha.py    # Hypha —— 把孢子链接拉取为已验证的明文菌核
```

## 快速开始 Quick Start

播种者（`wire` 字节来自 `Sclerotium.encrypt(cfg)`，见 `mycelium.protocol`）：

```python
from mycelium.interface.sower import GiteeClient, GitCodeClient, GithubClient

# 个人空间（namespace）由接口资料（GET /user）解析——没有 owner 参数。
client = GiteeClient(access_token, repo="my-feed-repo")
client.ensure_repo_exists()                # 缺失时创建
client.push("feed.dat", wire, commit_message="publish demo feed")

# 同样的流程用于 GitCode（或经 host="atomgit.com" 用 AtomGit）。
client = GitCodeClient(access_token, repo="my-feed-repo")
client.ensure_repo_exists()
client.push("feed.dat", wire, commit_message="publish demo feed")

# 同样的流程用于 GitHub——默认保留 raw.githubusercontent.com；
# 传 cdn=True 走 jsDelivr 镜像，或传自定义函数走其他镜像。
client = GithubClient(access_token, repo="my-feed-repo")
client.ensure_repo_exists()
client.push("feed.dat", wire, commit_message="publish demo feed")
link = client.spore_link("feed.dat", cfg.vk)  # 采摘者链接
```

采摘者：

```python
from mycelium.interface.picker import Hypha

sclerotium = Hypha().pull("mycelium://...")
```

## 添加新平台 Adding a New Platform

要发布到另一个 git 托管平台（如 GitLab），在 `sower/gitee.py` 旁新增同级模块，继承 `sower.base.GitPlatformClient` 并实现完整抽象契约；对于非 git 后端（如 WebDAV 服务器），继承 `sower.base.Storage` 并实现 `push(path, data)` 即可。
采摘者无需任何改动：`Hypha` 通过孢子链接里的普通 HTTPS URL 抓取，任何可被 HTTP 访问的主机都能工作。
