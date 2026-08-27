# 密码模块 crypto

本模块是 Mycelium 全部密码学的基础。设计采用"脑洞极其大开的加密流程"：**除发布者的签名私钥随机生成外，其余一切密钥与参数皆确定性派生**。
例如由私钥导出的验证公钥 `VK`，既用于验证签名，也用于派生加密主密钥——订阅者只需拿到极简的验证公钥，便可解密内容并验明发布者身份。

## 哈希模块 Hash

> 源码：[Hash.py](../../src/mycelium/crypto/Hash.py)

提供若干哈希函数的参数简化封装（固定参数，避免误用）：

- SHA-2 系列：`SHA224`（28 字节）、`SHA256`（32 字节）、`SHA384`（48 字节）、`SHA512`（64 字节）。
- SHA-3 系列：`SHA3_224`（28 字节）、`SHA3_256`（32 字节）、`SHA3_384`（48 字节）、`SHA3_512`（64 字节）。
- `HMAC(key, msg)`：HMAC-SHA-512（固定哈希算法）。
- `PBKDF2(pwd, salt, count)`：PBKDF2-HMAC-SHA-512，输出 32 字节。
- `HKDF(ikm, ctx)`：单步 HKDF（嵌套 HMAC-SHA-512 + 计数器字节），输出 32 字节，用于派生 GCM 子密钥。

完整 SHA-2/SHA-3 家族供 `vk2pad` 使用（见下文"配置对象"）。

## 加密模块 AES

> 源码：[AES.py](../../src/mycelium/crypto/AES.py)

提供 `GCM` 类，实现 AES-256-GCM 加解密。初始化方法接收主密钥 `mk`，以及元数据 `time`（整数）、`edition`（整数）、`guid`（可选；条目必填，频道省略）。

初始化时全部参数确定性派生：

1. 公共元数据 `COMMON = TIME(5B) || EDITION(3B)`；
2. HKDF 上下文 `CTX = "CHCTX" || COMMON`（频道）或 `"ITCTX" || GUID || COMMON`（条目），派生子密钥 `DEK = HKDF(mk, CTX)`；
3. GCM 随机数 `NONCE = TIME(6B) * 2`；
4. GCM 附加验证数据 `AAD = "CHAAD" || COMMON`（频道）或 `"ITAAD" || GUID || COMMON`（条目）。

加密逻辑（接收字符串明文 `pt`）：

1. 检查对象是否已被使用，已使用则抛 `RuntimeError`（单次使用，杜绝 nonce 重用）；
2. 加密得到密文与认证标签；
3. 返回 `TAG || CT`。

解密逻辑（接收 `TAG || CT`）：

1. 同样检查单次使用；
2. 分离 `TAG` 与 `CT`，解密并校验认证标签；
3. 校验失败抛 `ValueError`，成功返回明文。

## Edwards 曲线数字签名模块 EdDSA

> 源码：[EdDSA.py](../../src/mycelium/crypto/EdDSA.py)

- `Signer(sk)`：以 32 字节私钥构造签名器，`sign(data)` 产出 64 字节 Ed25519 签名。
- `Verifier(vk)`：以 32 字节公钥构造验证器，`verify(data, sign)` 返回布尔值。
- `get_pub(sk)`：由私钥导出公钥。

## 配置对象 crypto.Config

> 源码：**`__init__.py`**

用户的加解密配置由此对象统一管理。初始化只接收一个参数——32 字节签名私钥 `sk`，并导出验证公钥 `vk`。

主密钥 `mk`（用于 AES-256-GCM）采用懒加载 + 缓存策略，避免重复 PBKDF2 计算。推导过程（`vk2mk`）：

1. `D1 = SHA512(VK)`；
2. 密码 = `D1` 的奇下标字节，盐 = `D1` 的偶下标字节；
3. `D2 = SHA512(D1)`；`PRN = D2[31:33]`（偏移 31 处的 2 字节）转整数；
4. 迭代次数 `CNT = 100000 + PRN * 3`（范围 100,000–296,605）；
5. `MK = PBKDF2(PWD, SALT, CNT)`。

线格式混淆用的循环异或密钥流（pad）同样由 `VK` 派生（`vk2pad`，即懒加载的 `Config.pad` 属性）：
从 `key = VK` 开始，按 SHA-2/SHA-3 全系列顺序（2-224、2-256、2-384、2-512、3-224、3-256、3-384、3-512）依次 `key += f(key)`（对累积 key 求哈希）
得到 376 字节密钥流。`crypto.xor(data, key)` 将其循环应用到数据上，且自反（异或两次还原）。

使用方式：

- `crypto.new()`：新建配置，随机 32 字节私钥；
- `crypto.parse(data)` / `bytes(config)`：私钥的序列化往返（内存/旧格式）；
- `config.export_pem([passphrase])`：导出标准 PKCS#8 PEM（传入口令则加密）；
- `crypto.parse_pem(data[, passphrase])`：从 PEM 重建配置；
- `crypto.save(path, config[, passphrase])`：将配置原子写入 PEM 密钥文件（POSIX 下权限 0600）；
- `crypto.load(path[, passphrase])`：读取密钥文件（自动识别旧裸字节格式，平滑迁移）；
- `config.gen_signer()`：生成 Ed25519 签名器；
- `config.gen_cipher(time, edition[, guid])`：生成确定性 AES-GCM 对象；
- `config.pad` / `crypto.vk2pad(vk)`：线格式混淆密钥流；
- `crypto.xor(data, key)`：循环异或（自反）。

### 私钥文件存储 Key-File Storage

发布者签名私钥在磁盘上以标准 **PKCS#8 PEM** 文件保存（约定 `.key` 后缀），取代旧的"裸 32 字节 `.dat` 文件"约定：

- **格式标准**：`-----BEGIN PRIVATE KEY-----`，openssl 等工具可直接读取/转换；传 `passphrase` 时导出为 `-----BEGIN ENCRYPTED PRIVATE KEY-----`（PBKDF2 + AES-128-CBC），防止明文落盘；
- **原子写与权限**：`save` 先写同目录临时文件再 `os.replace`，避免半截文件；POSIX 下自动 `chmod 0600`，仅属主可读；
- **平滑迁移**：`load` 自动识别 PEM 与旧裸字节格式——历史 `publisher.dat`/`config.dat` 无需手工转换，读入后调用一次 `save` 即为 PEM；
- **口令来源由调用方决定**：`save`/`load` 只接收显式 `passphrase` 参数；示例脚本约定从 `MYCELIUM_KEY_PASSPHRASE` 环境变量读取（真实部署可改用交互提示或系统钥匙串）。

安全性说明：`Config` 的 `repr` 不包含私钥与主密钥，避免泄露进日志。

## 安全性考虑

大部分参数虽是确定性派生，但需要唯一性的参数（nonce）由派生算法保证不重用——只要 `(time, edition)` 不被复用。GCM 对象强制单次使用，从实现上杜绝误用。

忠告：Mycelium 只是一种加密**订阅**源的协议，链接的公开程度决定内容的定位——链接**公开**时，只宜发布博客、新闻、公告等**公开性质**（但明文因特殊原因被网络屏蔽）的内容；链接**只对一人或团队中的数人私下公开**时，也可以承载机密消息（共享密钥的群组广播、订阅者轮询拉取；链接一旦泄露即失密，且无法逐人撤销）。
