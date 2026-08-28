# Hash Module

> Source: [Hash.py](../../src/mycelium/crypto/Hash.py)

Thin wrappers around `hashlib`/`hmac` with fixed parameters (no misuse
surface):

- SHA-2: `SHA224` (28 B), `SHA256` (32 B), `SHA384` (48 B), `SHA512` (64 B).
- SHA-3: `SHA3_224` (28 B), `SHA3_256` (32 B), `SHA3_384` (48 B),
  `SHA3_512` (64 B).
- `HMAC(key, msg)` — HMAC-SHA-512 (fixed hash).
- `PBKDF2(pwd, salt, count)` — PBKDF2-HMAC-SHA-512 with a 32-byte output.
- `HKDF(ikm, ctx)` — single-step HKDF (nested HMAC-SHA-512 + counter byte),
  32-byte output, used to derive GCM sub-keys.

## Derived keys

`vk2mk` and `vk2pad` (see `README.md`, "Config Object") build on this
module:

- **`vk2mk`** (the AES master key): `D1 = SHA512(VK)`; password = the
  odd-indexed bytes of `D1`, salt = the even-indexed bytes; `D2 =
  SHA512(D1)`; `PRN = D2[31:33]` as an integer; iteration count
  `CNT = 100000 + PRN * 3` (range 100,000–296,605);
  `MK = PBKDF2(PWD, SALT, CNT)`.
- **`vk2pad`** (the wire-obfuscation keystream): start from `key = VK`,
  append `f(key)` for every SHA-2/SHA-3 algorithm in order (2-224, 2-256,
  2-384, 2-512, 3-224, 3-256, 3-384, 3-512), yielding a 376-byte
  keystream applied cyclically by `crypto.xor` (self-inverse).
