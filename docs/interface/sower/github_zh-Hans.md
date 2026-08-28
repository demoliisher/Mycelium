# GitHub 平台模块 GitHub Platform Module

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
