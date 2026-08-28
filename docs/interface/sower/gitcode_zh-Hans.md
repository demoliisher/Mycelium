# GitCode 平台模块 GitCode Platform Module

> 源码：[gitcode.py](../../../src/mycelium/interface/sower/gitcode.py)

GitCode 与 AtomGit 是**同一个平台的两个名字**：两个域名上的 API 完全一致。
`GitCodeClient` 默认使用 `gitcode.com`，也接受 `atomgit.com` 作为别名（通过 `host` 参数或 fork 源链接）。功能规模与 `GiteeClient` 对齐：

- **`repo` 模式** — 管理 `<namespace>/repo`：缺失时创建，然后向其中推送；
- **`fork` 模式** — 伪装模式：把 *GitCode* 源仓库复刻进本账户，**保留同名**；账户中已存在同名仓库时直接复用；
- 个人空间 `namespace` 由 `GET /user` 解析——**没有 `owner` 参数**；
- **暂不支持其他平台**（GitHub、Gitee……）——这类 fork 链接会被拒绝，并提示到 GitCode 网页手动导入。

平台差异：GitCode 的 contents API 对缺失文件返回 **HTTP 404**（Gitee 返回空列表），默认分支为 `main`。当 contents 写入在瞬时竞态重试后仍失败时，`push` 回退到经纯 Python 的 [git 推送后端](git_zh-Hans.md)（`GitPusher`）执行**真实 git push**——提交身份取自 GitCode 资料（登录名 + 资料邮箱），git 凭据为登录名 + 访问令牌作密码；若无法解析身份，则重新抛出原始 API 错误。

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
