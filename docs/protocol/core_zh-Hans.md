# 核心模块（Fruit / Sclerotium） Core

> 源码：[core.py](../../src/mycelium/protocol/core.py)

## 数据结构

### 果实 Fruit

| 字段         | 类型       | 描述                                      |
| ------------ | ---------- | ----------------------------------------- |
| `time`       | `int`      | 最后修改时间戳（秒）。                    |
| `edition`    | `int`      | 修订次数，从 `1` 开始，每次更新递增 1。   |
| `content`    | `str`      | 果实文本内容。                            |
| `guid`       | `UUID`     | 全局唯一标识符（v4）。                    |

**加密缓存 `_FruitCache`**：协议是确定性的——内容未变的果实重复加密必须产出相同密文。
缓存以验证公钥 `vk` 为键，保存 `(密文, 签名)`；一旦果实的明文负载（guid/time/edition/content）发生变化，缓存整体失效。

**方法**：

- `cls.new(content)` – 创建新果实：分配 guid，时间戳为当前时间，修订次数为 1；
- `ins.update(value)` – 更新内容，时间戳设为当前时间，修订次数 +1；
- `ins.encrypt(config)` – 用配置对象加密并签名（签名覆盖 guid、time、edition、content），返回 protobuf 消息；
- `cls.decrypt(msg, VK)` – 用验证公钥 `VK` 解密并验证 protobuf 消息 `msg`，返回明文果实；失败抛 `ValueError`。

### 菌核 Sclerotium

| 字段         | 类型                 | 描述                            |
| ------------ | -------------------- | ------------------------------- |
| `time`       | `int`                | 最后修改时间戳（秒）。          |
| `edition`    | `int`                | 修订次数，从 `1` 开始。         |
| `content`    | `str`                | 菌核文本内容（如标题）。        |
| `fruits`     | `list[Fruit]`        | 以创建时间倒序的果实列表。      |
| `_table`     | `dict[UUID, Fruit]`  | 按 guid 快速查找果实的表。      |

**方法**：

- `cls.new(content)` – 创建新菌核，时间戳为当前时间，修订次数为 1；
- `ins.entry(content)` – 创建并添加新果实（内部调用 `Fruit.new`），菌核时间戳同步更新；
- `ins.update(value)` – 更新菌核内容，修订次数 +1；
- `ins[guid]` – 按 guid 查找果实；
- `ins.encrypt(config)` – 加密菌核内容并签名；签名覆盖菌核元数据与**所有果实的签名负载**（顺序绑定）；
- `cls.decrypt(msg, VK)` – 解密并验证 protobuf 消息（bytes 或消息对象），返回明文菌核。

注意：菌核每次加密都被视为一次新发布，`encrypt` 会把 `time` 刷新为当前时间戳，因此 nonce 不会重用（此处不做缓存）。

## 加密工作流 Cryptography Workflow

所有加解密使用统一的 `Config` 对象（仅发布者持有，见 `mycelium.crypto`）：

- **AES-256-GCM 部分**：`mk` —— 32 字节主密钥，由验证公钥 `VK` 经 `vk2mk` 确定性派生
  （PBKDF2：密码/盐取自 `SHA512(VK)` 的奇偶下标字节，迭代次数取自 `SHA512(SHA512(VK))`）。
- **Ed25519 部分**：`signer` —— 由私钥 `SK` 构造的签名器；`vk` —— 验证公钥。

由于 `MK` 由 `VK` 派生，订阅者**只需 `VK`** 即可同时解密（AES-GCM）与验签（Ed25519），密钥分发被压缩为单个值。

### 线格式混淆 Wire Obfuscation

在 protobuf 序列化之上，菌核字节还会被一层**循环异或**混淆，使文件托管平台看到的是无法辨认的字节而非 protobuf 结构。
循环异或的密钥流（pad）仅由 `VK` 派生（`crypto.vk2pad`，即 `Config.pad` 属性）：

```python
key = VK
for f in [SHA-2 224/256/384/512, SHA-3 224/256/384/512]:
    key += f(key)          # 对累积 key 求哈希
```

结果共 376 字节（32 + 28+32+48+64 + 28+32+48+64），对 protobuf 二进制循环异或：`wire = XOR(protobuf, pad)`。
由于 `VK` 公开，这是**混淆而非加密**——目的是向托管平台与粗心观察者隐藏 protobuf 结构。

### Fruit

果实与菌核共享 AES-GCM 子密钥派生（全部确定性，见 `../../src/mycelium/crypto/AES.py`）：

1. 输入：`mk`（主密钥）、`time`、`edition`、`guid`（菌核无 guid）；
2. 公共元数据 `COMMON = TIME(5B) || EDITION(3B)`；
3. HKDF 上下文：`CTX = "ITCTX" || GUID || COMMON`（果实）或 `"CHCTX" || COMMON`（菌核）；
4. 子密钥 `DEK = HKDF(mk, CTX)`；
5. GCM 随机数：`NONCE = TIME(6B) * 2`；
6. 附加验证数据：`AAD = "ITAAD" || GUID || COMMON`（果实）或 `"CHAAD" || COMMON`（菌核）。

#### 加密与序列化

1. 按上述元数据派生加密对象；
2. 加密 `content`，密文布局为 `TAG(16B) || CIPHERTEXT`；
3. 用签名器对明文负载签名（果实：`GUID || TIME || EDITION || CONTENT`）；
4. 组装 protobuf 消息（`time`、`edition`、密文、`guid`、签名）。

返回 protobuf 消息对象。

#### 解密与验证

1. 按同一元数据派生加密对象；
2. 解密出明文内容；
3. 重建明文 `Fruit`；
4. 用 `VK` 验证签名，失败抛 `ValueError`。

返回明文 `Fruit`。

### Sclerotium

菌核没有 guid：加密对象直接以 `mk` 派生（`CTX = "CHCTX" || TIME(5B) || EDITION(3B)`）。

#### 加密与序列化（菌核）

1. 每次加密视为一次新发布：`time` 刷新为当前时间戳；
2. 按 `fruits` 的顺序逐个加密果实；
3. 签名负载 = 菌核元数据 + 全部果实签名负载（顺序绑定，防重排）；
4. 组装 protobuf 消息（`time`、`edition`、菌核密文、签名、果实列表）；
5. 将消息序列化为字节，并用 pad 循环异或（见"线格式混淆"）。

返回混淆后的线格式字节（`Sclerotium.encrypt`）。

#### 解析与验证

1. 用同一 pad 反向异或，导入 protobuf 消息；
2. 解密菌核内容；
3. 按相同顺序解密并验证每颗果实；
4. 重建 `fruits` 与 `_table`；
5. 验证菌核整体签名，失败抛 `ValueError`。

全部通过后，菌核被视为真实且未被篡改。

## 安全性考虑

- **主密钥保密性**：主密钥经 PBKDF2 派生，迭代次数 100,000–296,605，抵抗暴力破解。
- **Nonce 唯一性**：GCM nonce 由 `time` 确定性派生；只要同一 `(time, edition)` 不被复用即安全。
  协议通过每次更新严格递增 `edition` 保证这一点；菌核每次加密刷新 `time`，天然不重用 nonce。
- **签名绑定**：菌核签名覆盖元数据与全部果实签名，将内容集合及其顺序整体绑定。
- **单一密钥分发**：`MK` 由 `VK` 确定性派生，订阅者仅需验证公钥即可解密与验签，无需额外密钥协商。

## Proto 定义

protobuf 层定义见 `../../src/mycelium/protocol/feed.proto`（`feed_pb.py` 为旁边的生成代码，勿手改，以 `feed_pb as pb` 方式导入）。线上传输的是该消息序列化后再经 pad 循环异或的字节（见"线格式混淆"）：

```protobuf
message Fruit {
    bytes time = 1;      // int2bytes(Unix 时间戳)
    bytes edition = 2;   // int2bytes(修订次数)
    bytes content = 3;   // TAG || 密文
    bytes guid = 4;      // 16 字节 UUID
    bytes sign = 5;      // 64 字节 Ed25519 签名
}

message Sclerotium {
    bytes time = 1;
    bytes edition = 2;
    bytes content = 3;   // TAG || 密文
    bytes sign = 4;      // 覆盖元数据 + 全部果实签名的 64 字节签名
    repeated Fruit fruits = 5;
}
```
