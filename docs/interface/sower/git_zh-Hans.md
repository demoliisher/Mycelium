# Git 推送后端

> 源码：[git.py](../../../src/mycelium/interface/sower/git.py)

`GitPusher` 是基于 [dulwich](https://github.com/jelmer/dulwich) 的极简纯
Python 单文件 git 推送，走 git smart HTTP 协议——**无需安装 git 可执行
文件**。唯一写入路径是真 git push 的平台模块（CNB 没有 contents 写 API）
用它替代调用系统 `git`，从而消除一整类用户环境障碍：

- 用户机器上不需要安装 git 客户端，也不必配置 PATH；
- 提交身份由调用方直接写入 commit 对象（身份来自平台 API），无需设置
  `git config user.name/email`——也无需压制 credential helper、Git
  Credential Manager 弹窗或终端提示；
- 推送完全在内存中进行：无 clone、无工作树、无临时凭据存储文件。

## API

```python
pusher = GitPusher("https://cnb.cool/mycelium/my-feed", "cnb", token)
head = pusher.head("main")              # 远端 tip（hex sha）或 None
result = pusher.push_file(
    "main", "feed.dat", b"...", "Create file feed.dat",
    "Rainbow", "rainbow@example.com",   # author == committer，原样写入
)
# -> {"commit": {"sha": "..."}, "message": "Create file feed.dat"}
```

`push_file` 在内存中构造对象——包含文件字节的 blob、承载路径的 tree
（嵌套路径变成嵌套 tree）、携带给定作者/提交者身份的 commit——以远端
分支当前 tip 为 parent（新仓库得到根提交，同时消除了「分支仍在初始化」
的瞬时竞态），再用 `client.send_pack` 上传对象并快进 `refs/heads/<branch>`。

`url` 由 `dulwich.client.get_transport_and_path` 解析，因此本地文件系统
路径或 `file://` URL 同样可用——单元测试（`tests/interface/test_git.py`）
无需网络即可对本地裸仓库执行真实推送。

## 错误

dulwich 抛出自己的异常；`GIT_ERRORS` 是推送可能抛出的异常元组（协议错误、
`NotGitRepository`、401/407 认证错误），平台模块的 `push` 在 git 写入周围
捕获它。`is_transient_git_error(exc)` 告诉调用方该失败是像新仓库竞态或
网络抖动（值得重试），还是认证失败或服务端拒绝 pack（不值得重试）。

## 备用模式

`GitPlatformClient`（见 [base.py](README.md)）提供可选的 git 推送备用
模式：正常写入路径是 contents API 的平台（Gitee、GitCode、GitHub）可覆写
`_git_identity` 与 `_git_remote`，从平台 API 解析提交身份并给出目标仓库的
git 凭据；当 contents API 写入在瞬时竞态重试后仍失败时，`push` 回退到
`GitPusher`。无法解析身份时，则重新抛出原始 API 错误。
