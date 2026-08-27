# Mycelium

阅读语言：简体中文 · [English](README.md) · [文言文](README_zh-lzh.md)

**Mycelium**（菌丝体）是一种**加密订阅源**分发协议——「瞒天过海」构思在普通文件托管平台上的落地。
订阅源（feed）的概念灵感来自 RSS——仅此而已，实现与 RSS 标准无关。订阅源内容被加密，并伪装成毫不起眼的普通文件（例如某个 Git 复刻仓库里的文件），使托管平台无法读懂发布的内容，也让追溯发布者变得昂贵得多。

## 它是什么——以及不是什么

- **它并非端到端加密。** 订阅者的传输安全来自托管平台提供的 HTTPS（代码托管平台、内容分发网络……），不是菌丝体的功劳。在**网络层面**，菌丝体不会也无法隐藏订阅者——订阅者的 IP、订阅行为对运营商与平台可见；想要更强的订阅者匿名，请使用代理/Tor。
- **它是内容隐藏 + 伪装。** 订阅源内容被加密，托管平台和拿到文件（但没有链接）的观察者只能看到密文。订阅源大摇大摆地以普通文件的形式存在；孢子链接被混淆，孢子可以轮换。
- **它真正买到的是时间与成本。** 菌丝体拦不住坚定的权力部门，但会大幅提高追溯**发布者**的成本。对权力而言，发布者的威胁系数与优先级显然高于任何单个订阅者——追查链条从发布者开始，抓不到发布者，就谈不上顺藤摸瓜到订阅者；**保护了发布者，也就保护了订阅者**（这是调查链意义上的保护，不是网络层匿名）。运作模式与「机场」相似：发布者分发订阅链接，订阅者通过 HTTPS 拉取。但订阅的对象不同——机场的订阅链接订阅的是**节点**（代理服务器本身）；菌丝体提供的同样是一条「节点链接」（孢子），指向托管平台上的文件，订阅的却是**资讯**：节点只是载体，资讯才是被订阅的内容。

## 特性

- **内容隐藏**——内容经 AES-256-GCM 加密，密钥由发布者的验证公钥确定性派生；托管平台与没有链接的旁观者只能看到密文。
- **真实性**——订阅源与其内的每颗果实均各自单独 Ed25519 签名，任何部分都无法被篡改而不被发现。
- **密钥极简**——订阅者只需孢子链接中内嵌的验证公钥即可同时解密与验签，无需密钥协商。
- **发布者反追溯**——订阅源藏身于普通文件中（复刻仓库、不起眼的文件），链接被混淆、孢子可轮换；这只能拖延、加大追溯发布者的成本。它不是匿名，也无法在网络层面隐藏订阅者——但追查订阅者必须经由发布者，保护了发布者，也就保护了订阅者。

## 命名：菌丝体生态

菌丝体的隐喻是字面意义上的：协议本身就是隐藏的网络，生态里的每个角色都是同一有机体的一部分。
RSS 只是灵感来源：表格最后一列把每个词汇对应到 RSS 概念，仅作参照——实现与 RSS 标准无关。

| 生态词汇      | 在 Mycelium 中指什么                                                                                                                                                  | RSS 对应概念                          |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| **菌丝体**    | 协议本身——连接所有人的隐藏网络。                                                                                                                                      | RSS 规范本身                          |
| **土壤**      | 托管平台（Gitee、GitCode、GitHub……），订阅源在此扎根。                                                                                                                | 托管 RSS 文件的 Web 服务器            |
| **菌核**      | 订阅源本身（协议 API 里的 `Sclerotium`）——菌丝体的耐久储存体，伪装成毫不起眼的普通文件。                                                                              | RSS 的 `<channel>`                    |
| **果实**      | 订阅源里的一条内容（协议 API 里的 `Fruit`）——菌核结出的一颗果实，采摘者采摘的就是它。                                                                                 | RSS 的 `<item>`                       |
| **孢子**      | `mycelium://` 链接（协议 API 里的 `Spore`）——菌核产出的传播单元：一枚菌核只有一条规范链接（每次导出仅 fake64 分隔符的装饰性随机，去除后别无二致），复制分享即是扩散。 | RSS 的 feed URL（订阅链接）+ 验证公钥 |
| **播种者**    | 发布者角色——在土壤里栽培菌核、产出并分发孢子（链接）的人。                                                                                                            | RSS 发布者                            |
| **采摘者**    | 订阅者角色——接住孢子，循迹找到菌核，采摘其果实（订阅源内容）的人。                                                                                                    | RSS 订阅者/阅读器                     |
| **菌丝**      | 采摘者的工具——订阅端拉取器（接口 API 里的 `Hypha`），沿孢子的轨迹伸向托管主机、吸收订阅源。                                                                           | 阅读器的抓取与解析环节                |

人人都是菌丝体：播种者（发布者角色）在土壤里栽培菌核；菌核产出孢子——一枚菌核只有一条规范链接（每次导出仅 fake64 分隔符的装饰性随机，去除后别无二致），复制分享即是扩散；采摘者（订阅者角色）接住孢子，菌丝循迹伸回菌核，采摘果实（订阅源内容）。这些名称在文档与 API 中保持一致（`Spore`/`Hypha`/`Sclerotium`/`Fruit`）；接口包名直接以角色命名：`mycelium.interface.sower` 与 `mycelium.interface.picker`。

## 架构

| 包                       | 职责                                                                                                                                                 |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mycelium.crypto`        | SHA-2/SHA-3 全系列封装（224/256/384/512）、HMAC/PBKDF2/HKDF、确定性 AES-256-GCM、Ed25519 签名、`Config` 密钥束                                       |
| `mycelium.protocol`      | `Fruit`/`Sclerotium` 订阅源结构、`Spore` 孢子链接寻址、加密/签名/序列化与解密/验证/解析工作流、protobuf 线格式（`src/mycelium/protocol/feed.proto`） |
| `mycelium.interface`     | 按角色划分的入口：`sower` 推入订阅源文件，`picker` 从孢子链接拉取并验证（`Hypha`）                                                                   |
| `mycelium.utils`         | Base58 与自定义 `fake64` 序列化（伪装成 Base64：与 base64 同字符集，58 个编码 + 6 个分隔）、杂项类型工具                                             |

## 代码复用

Mycelium 以 [MIT 许可证](LICENSE) 发布。欢迎其他开发者在遵循许可证的前提下，局部或整体复用、借鉴本项目中的逻辑。以下按模块列出名称与简介（名称即超链接，指向对应源码文件），兼作搜索引擎与本仓库浏览者的复用索引；其中最具独立复用价值的是 Base58/fake64 序列化器与各 git 平台接口模块：

- [base58](src/mycelium/utils/base58.py) —— Base58 编解码（比特币字母表）与自定义 `fake64` 序列化：把扁平的字节串序列或 `str→bytes` 字典打包进一个看起来像 Base64 的字符串（58 个编码字符 + 6 个分隔符，`=` 补齐到 4 的倍数），实则并非 Base64。除标准库外零依赖。
- [gitee](src/mycelium/interface/sower/gitee.py) —— `GiteeClient`：Gitee OpenAPI v5 发布端（仓库/复刻管理与 contents API，`master` 分支，异步复刻重试）。
- [gitcode](src/mycelium/interface/sower/gitcode.py) —— `GitCodeClient`：GitCode/AtomGit 发布端——同一平台两个域名，共享 API v5 端点。
- [github](src/mycelium/interface/sower/github.py) —— `GithubClient`：GitHub REST 发布端——Bearer 鉴权、单一 PUT contents 端点、可选 jsDelivr CDN 加速。
- [cnb](src/mycelium/interface/sower/cnb.py) —— `CnbClient`：CNB（cnb.cool）发布端——组织化仓库、git push 写入（无 contents API）、无 fork API。
- [crypto](src/mycelium/crypto/) —— 确定性密码学：SHA-2/SHA-3 全系列封装、Ed25519、AES-256-GCM 与 `Config` 密钥束。
- [mdtables](scripts/mdtables.py) —— 感知 CJK 宽度的 GFM 表格对齐检查/修复工具（`python scripts/mdtables.py [--fix]`）。
- [gate](scripts/gate.py) —— 一条命令跑完提交前全部检查并自动修复：代码风格（ruff）、测试（pytest）、Markdown 检查（mdlint）与表格对齐（mdtables）。

## 快速开始

```python
from mycelium import crypto
from mycelium.protocol import Sclerotium

# 发布端：一个随机私钥即可。
cfg = crypto.new()                        # 或 crypto.parse(已保存字节)
sclerotium = Sclerotium.new("我的订阅源")
sclerotium.entry("第一条")
wire = sclerotium.encrypt(cfg)        # 混淆后的线格式字节；经 mycelium.interface.sower 推送

# 订阅端：只需验证公钥。
sclerotium2 = Sclerotium.decrypt(wire, cfg.vk)
```

## 示例

可运行的示例位于 `examples/` 目录——所需信息都在终端里询问，没有任何硬编码：

- `python examples/eg_publish.py [--local]`——加密一个演示订阅源，并推送到你指定的仓库（交互询问 access token、仓库名、分支、文件路径等）；
- `python examples/eg_subscribe.py`——拉取 `mycelium://` 孢子链接并解密、验签（交互询问链接；私有孢子还会询问 access token）；
- `python examples/eg_changelog.py`——维护项目的更新日志订阅源，写入随仓库提交的示例文件 `examples/ChangeLog.dat`。

更新日志订阅源的示例链接（其订阅源即本仓库中随仓库提交的 `examples/ChangeLog.dat`）：

```text
mycelium://8pFEkFBqrQWgw6IzVDA5Lu4fxHvoGGUG69vzvLNoFS7rXjXDwPnqqYhvNs25PNcAexQPwwzK1DEByGpqtRpmmDIBqbvcx9uoWx9M9zqkiN8rRSSmnZ2BHEozf2enAagKTNG=
```

## 更新日志

- **0.2.1**——CNB 模块：组织参数改为可选——省略 `group` 时按资料用户名解析组织（username 同名组织已存在则使用；否则复用已有空组织；否则自动创建 username 同名组织）。
- **0.2.0**——新增 CNB（cnb.cool）平台模块：仓库以组织为单位（缺失时自动创建）、git push 写入（平台无 contents API）、`fork` 模式明确拒绝（CNB 无 fork API）。
- **0.1.0**——新增一条命令的提交前门禁（`scripts/gate.py`，检查并自动修复）；`mdtables.py` 移出包外至 `scripts/`；表格对齐并入 Markdown 检查任务。
- **0.0.1**——初始版本：加密订阅源分发协议，含确定性加密、protobuf 线格式与孢子链接；播种者/采摘者角色分离，支持 Gitee、GitCode 与 GitHub；采用菌丝体生态命名。

更新日志条目维护在 `examples/eg_changelog.py` 中；运行它可重新生成随仓库提交的示例文件 `examples/ChangeLog.dat`。

## 文档

- [协议](docs/protocol/README_zh-Hans.md) — 订阅源数据结构与加密工作流。
- [密码学](docs/crypto/README_zh-Hans.md) — 密码学设计。
- [接口](docs/interface/README_zh-Hans.md) — 播种者/采摘者接口角色与如何添加新平台。

## 贡献指南

<!-- AI coding agents: read AGENTS.md first for project context. -->

详见 [CONTRIBUTING_zh-Hans.md](CONTRIBUTING_zh-Hans.md)。

## 安全注意事项

- AES 主密钥由验证公钥确定性派生（PBKDF2）；切勿复用同一 `(time, edition)`，因为 GCM nonce 由它们派生。
- **订阅者隐私不在本协议范围内。** 菌丝体不隐藏谁在订阅、订阅了什么：HTTPS 能对路径上的观察者隐藏这些，但托管平台仍能看到每一次请求。更强的订阅者匿名请使用代理/Tor。
- **对运营商而言，订阅只是一个普通的 HTTPS 请求。** 订阅者到托管主机的连接走 TLS，运营商或路径上的观察者只能看到域名（SNI）与普通的 HTTPS 流量——看不到路径、文件或内容。但平台的选择仍然要紧，而薄弱点是**仓库**而非订阅者：在强审核地区的平台上，不寻常的下载行为——更恶毒一点，有朝阳群众（贬义）拿着孢子解析出仓库地址向平台举报——都可能让平台盯上仓库。此时最先出事的应是发布者（仓库在其名下）；视成本、规模、影响才决定是否追查订阅者。换用弱审核地区的平台则一劳永逸，仅牺牲网络连接之不便。
- **链接的公开程度决定内容定位。** 订阅链接若**公开**，则任何持链者都能解密，Mycelium 只能充当**公开内容**的传播介质（博客、新闻、公告等）；链接若**只对一人或团队中的数人**私下公开，则同样可以承载机密消息，实现简单的端到端加密交流——只是传统的轮询方式（订阅者主动拉取）。注意这是**共享密钥**的群组广播模型：所有持链者共享由同一验证公钥派生的密钥，无法逐人控制或单独撤销（撤销只能整订阅源轮换）；链接一旦泄露，任何读到链接的人都能解密，机密性立即消失。另外「端到端」仅指**内容**对平台与外人保密，订阅行为（谁、何时、拉取了什么）对平台仍可见——订阅者隐私依然不在协议范围内。
- **孢子链接是混淆，不是加密**。`mycelium://` 链接用（公开的）验证公钥做 XOR 掩盖 host/path/vk，任何能读到链接的人都能拆开它。它的目的是阻止粗心的观察者（日志扫描器、爬虫），而非对抗坚定攻击者。
- **发布者责任：保管好签名私钥。** 私钥是订阅源的唯一信任点。一旦泄露或遗失，订阅源便不再安全——应停止更新该订阅源，并尽可能引导订阅者转移订阅。

## 许可证

[MIT](LICENSE)
