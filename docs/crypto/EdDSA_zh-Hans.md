# Edwards 曲线数字签名模块 EdDSA

> 源码：[EdDSA.py](../../src/mycelium/crypto/EdDSA.py)

- `Signer(sk)`：以 32 字节私钥构造签名器，`sign(data)` 产出 64 字节 Ed25519 签名。
- `Verifier(vk)`：以 32 字节公钥构造验证器，`verify(data, sign)` 返回布尔值。
- `get_pub(sk)`：由私钥导出公钥。
