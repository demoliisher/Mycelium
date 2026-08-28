# 孢子 Spore

> 源码：[spore.py](../../src/mycelium/protocol/spore.py)

`Spore` 打包了订阅者所需的一切——host、path 与发布者验证公钥——并可导出为带自定义 `mycelium://` 协议头的紧凑链接（解析时协议头**可选**，裸负载同样接受）。负载经 XOR 混淆并用 `fake64`（Base58 + 6 个分隔符，伪装成 Base64）序列化，字段不可直接识读；注意这只是轻量**混淆**（以公开的 `vk` 为密钥），不是加密。

在菌丝体生态命名中，孢子由菌核——订阅源——产生并携带其地址：一个菌核有且只有一条规范链接，各次导出仅 cosmetic fake64 分隔符不同，因此链接的副本都是同一个孢子，分享链接即传播孢子。接住孢子的采摘者循着轨迹回到宿主。`Spore` 是纯数据类：只负责生成与解析孢子链接。抓取订阅源文件是采摘者的职责——见 `mycelium.interface.picker.Hypha`。

- `Spore(host, path, vk)` — 纯数据类；
- `spore.export()` — 序列化为 `mycelium://` 链接；
- `protocol.parse(link)` — 解析回 `Spore`（`mycelium://` 协议头可选）。
