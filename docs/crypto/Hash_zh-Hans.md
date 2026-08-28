# 哈希模块 Hash

> 源码：[Hash.py](../../src/mycelium/crypto/Hash.py)

提供若干哈希函数的参数简化封装（固定参数，避免误用）：

- SHA-2 系列：`SHA224`（28 字节）、`SHA256`（32 字节）、`SHA384`（48 字节）、`SHA512`（64 字节）。
- SHA-3 系列：`SHA3_224`（28 字节）、`SHA3_256`（32 字节）、`SHA3_384`（48 字节）、`SHA3_512`（64 字节）。
- `HMAC(key, msg)`：HMAC-SHA-512（固定哈希算法）。
- `PBKDF2(pwd, salt, count)`：PBKDF2-HMAC-SHA-512，输出 32 字节。
- `HKDF(ikm, ctx)`：单步 HKDF（嵌套 HMAC-SHA-512 + 计数器字节），输出 32 字节，用于派生 GCM 子密钥。

## 派生密钥 Derived keys

`vk2mk` 与 `vk2pad`（见 `README_zh-Hans.md` 的「配置对象」）建立在本模块之上：

- **`vk2mk`**（AES 主密钥）：`D1 = SHA512(VK)`；密码 = `D1` 的奇下标字节，盐 = `D1` 的偶下标字节；`D2 = SHA512(D1)`；`PRN = D2[31:33]` 转整数；迭代次数 `CNT = 100000 + PRN * 3`（范围 100,000–296,605）；`MK = PBKDF2(PWD, SALT, CNT)`。
- **`vk2pad`**（线格式混淆密钥流）：从 `key = VK` 开始，按 SHA-2/SHA-3 全系列顺序（2-224、2-256、2-384、2-512、3-224、3-256、3-384、3-512）依次 `key += f(key)`，得到 376 字节密钥流，由 `crypto.xor` 循环应用（自反）。
