# EdDSA Module

> Source: [EdDSA.py](../../src/mycelium/crypto/EdDSA.py)

- `Signer(sk)` — signer bound to a 32-byte secret key; `sign(data)`
  produces a 64-byte Ed25519 signature.
- `Verifier(vk)` — verifier bound to a 32-byte public key;
  `verify(data, sign)` returns a boolean.
- `get_pub(sk)` — derives the public key from a secret key.
