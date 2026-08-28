# 播种者接口 Sower

Mycelium 的播种者：把加密后的订阅源文件推入托管后端，供采摘者拉取。

## 平台模块 Platform modules

每个受支持平台有独立文档：

- [Gitee](gitee_zh-Hans.md) — `GiteeClient`（Gitee API v5）
- [GitCode](gitcode_zh-Hans.md) — `GitCodeClient`（AtomGit 别名）
- [GitHub](github_zh-Hans.md) — `GithubClient`
- [CNB](cnb_zh-Hans.md) — `CnbClient`（真实 `git push`；提交身份取自平台 API）

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

## 添加平台 Adding a Platform

对于另一个 git 托管平台，在 `gitee.py` 旁新增同级模块（如 `gitlab.py`），继承 `GitPlatformClient` 并实现完整契约（构造函数、类属性与上面列出的每个抽象方法）；
对于非 git 后端（如普通 WebDAV 服务器），直接继承 `Storage` 并实现 `push`。
在 `sower/__init__.py` 中与其他客户端一起导出，即可接入同一套播种工作流。平台文档按 `<平台名>.md`（+ 可选 `<平台名>_zh-Hans.md`）命名，放在本目录。
