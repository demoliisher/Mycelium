# 密码模块 crypto

Mycelium 全部密码学的基础：**除发布者的签名私钥随机生成外，其余一切密钥与参数皆确定性派生**——验证公钥 `VK` 派生 AES 主密钥与线格式混淆 pad，订阅者只需极简的 `VK` 便可解密内容并验明发布者身份。

## 模块 Modules

- [Hash](Hash_zh-Hans.md) — SHA-2/SHA-3 封装、HMAC、PBKDF2、HKDF；含 `vk2mk` / `vk2pad` 的派生细节
- [AES](AES_zh-Hans.md) — AES-256-GCM（单次使用的 `GCM`）
- [EdDSA](EdDSA_zh-Hans.md) — Ed25519 签名器/验证器

## 配置对象 crypto.Config

> 源码：**`__init__.py`**

用户侧的统一入口，以 32 字节签名私钥 `sk` 构造（导出 `vk`，并懒加载 `mk` 与 `pad`）：

- `crypto.new()` — 新建配置，随机 32 字节私钥；
- `crypto.parse(data)` / `bytes(config)` — 私钥的序列化往返（内存/旧格式）；
- `config.export_pem([passphrase])` / `crypto.parse_pem(data[, passphrase])` — 标准 PKCS#8 PEM 往返；
- `crypto.save(path, config[, passphrase])` / `crypto.load(path[, passphrase])` — 密钥文件（见下）；
- `config.gen_signer()` — 生成 Ed25519 签名器；
- `config.gen_cipher(time, edition[, guid])` — 生成确定性 AES-GCM 对象；
- `config.pad` / `crypto.vk2pad(vk)` — 线格式混淆密钥流；
- `crypto.xor(data, key)` — 循环异或（自反）。

### 私钥文件存储 Key-File Storage

发布者签名私钥在磁盘上以标准 **PKCS#8 PEM** 文件保存（约定 `.key` 后缀），取代旧的"裸 32 字节 `.dat` 文件"约定：

- **格式标准**：`-----BEGIN PRIVATE KEY-----`，openssl 等工具可直接读取/转换；传 `passphrase` 时导出为 `-----BEGIN ENCRYPTED PRIVATE KEY-----`（PBKDF2 + AES-128-CBC），防止明文落盘；
- **原子写与权限**：`save` 先写同目录临时文件再 `os.replace`，避免半截文件；POSIX 下自动 `chmod 0600`，仅属主可读；
- **平滑迁移**：`load` 自动识别 PEM 与旧裸字节格式——历史 `publisher.dat`/`config.dat` 无需手工转换，读入后调用一次 `save` 即为 PEM；
- **口令来源由调用方决定**：`save`/`load` 只接收显式 `passphrase` 参数；示例脚本约定从 `MYCELIUM_KEY_PASSPHRASE` 环境变量读取（真实部署可改用交互提示或系统钥匙串）。

安全性说明：`Config` 的 `repr` 不包含私钥与主密钥，避免泄露进日志。

## 安全性考虑

需要唯一性的参数（nonce）由确定性派生保证不重用——只要 `(time, edition)` 不被复用。GCM 对象强制单次使用，从实现上杜绝误用。
