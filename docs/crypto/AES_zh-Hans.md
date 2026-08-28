# 加密模块 AES

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
