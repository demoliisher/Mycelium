# Gitee 平台模块 Gitee Platform Module

> 源码：[gitee.py](../../../src/mycelium/interface/sower/gitee.py)

`GiteeClient` 是针对 Gitee 仓库（Gitee API v5）的参考实现，绑定**恰好一个**目标，由两个**互斥**的构造参数选定：

- **`repo` 模式** — 管理 `<namespace>/repo`：缺失时创建，然后向其中推送；
- **`fork` 模式** — 伪装模式：把 *Gitee* 源仓库复刻进本账户，**保留同名**（Gitee 复刻 API 不支持自定义名称）。若账户中已存在同名仓库（例如之前复刻过），则直接复用，不再重复复刻。

个人空间 `namespace`（个人空间地址）由授权用户资料（`GET /user`）在首次使用时自动解析并缓存——**没有 `owner` 参数**，因此不可能输错属主。

**暂不支持其他平台**（GitHub、GitLab……）：Gitee OpenAPI v5 没有导入/clone 接口，这类 fork 链接会被拒绝，并提示到 Gitee 网页手动导入。

> **为避免污染开源社区，请勿向上游仓库提交 PR**——复刻副本是伪装容器，不是贡献。

- **推送** — `push(path, data, commit_message=...)` 通过 contents API 创建或更新文件：POST 创建（无需 sha），PUT 更新（需当前 blob sha）。当 contents 写入在瞬时竞态重试后仍失败时，`push` 回退到经纯 Python 的 [git 推送后端](git_zh-Hans.md)（`GitPusher`）执行**真实 git push**——提交身份取自 Gitee 资料（登录名 + 资料邮箱），git 凭据为登录名 + 访问令牌作密码；若无法解析身份，则重新抛出原始 API 错误。

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
