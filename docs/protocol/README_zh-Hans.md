# 订阅源协议模块 Protocol

Mycelium 协议中的订阅源数据结构和加密工作流：两个明文类经统一 `Config` 加密与签名，序列化为经混淆的 protobuf 线格式，并以 `mycelium://` 孢子链接寻址。

## 模块 Modules

- [core](core_zh-Hans.md) — `Fruit` / `Sclerotium` 数据结构、加密工作流与 protobuf 线格式
- [spore](spore_zh-Hans.md) — `mycelium://` 孢子链接寻址

## 概览

协议层定义了两个明文类（未加密，所有数据明文存储），字段与 Protocol Buffer 报文（详见 `core_zh-Hans.md`）一一对应：

- **Fruit（果实）**：一条独立的内容——菌核结出的一颗果实，例如博客帖子、新闻文章。
- **Sclerotium（菌核）**：一批果实汇成的订阅源，例如出版刊物、资讯专题。在生态命名中，订阅源报文本身就是菌核——生长在土壤里的耐久储存体；采摘者循着孢子的轨迹回到菌核，采摘果实。
