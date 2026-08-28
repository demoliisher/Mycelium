# 采摘者接口 Picker

Mycelium 的采摘者：把孢子链接变成已验证的明文菌核。生态上：孢子带着通往菌核的轨迹——`pull` 循迹而去，采摘果实（订阅源内容）。

## 菌丝 Hypha

> 源码：[hypha.py](../../../src/mycelium/interface/picker/hypha.py)

`Hypha.pull(link)` 完成整条订阅管线：

1. **解析** `mycelium://` 孢子链接为 host / path / 验证公钥（`mycelium.protocol.parse`）；
2. **下载** 从孢子经 HTTPS 抓取订阅源文件（下载由菌丝负责——`Spore` 是纯数据类）；
3. **解密并验签** 用孢子内嵌的验证公钥完成（`Sclerotium.decrypt`），得到明文菌核。

菌丝与传输平台无关：它只需要一个可经 HTTPS 访问的 URL，任何普通 HTTP 主机都能工作——不限于 Gitee。

默认匿名下载。对于需要认证的主机（如私有 Git 仓库），传入携带凭证的预配置 `requests.Session`；该会话只携带凭证，永远不会接触到孢子链接。

## 快速开始 Quick Start

```python
from mycelium.interface.picker import Hypha

sclerotium = Hypha().pull("mycelium://...")           # 公开孢子，匿名
sclerotium = Hypha(session=token_session).pull(link)  # 私有孢子，带令牌
```

## 注意事项 Notes

- 拉取失败时抛 `ValueError`（链接无效，或解密/验签失败）或 `ConnectionError`（孢子不可达）。
- `pull` 是 Mycelium 中获取订阅源内容的唯一途径。播种者刻意没有自己的 pull（见 `mycelium.interface.sower`）。
