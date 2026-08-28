# AES Module

> Source: [AES.py](../../src/mycelium/crypto/AES.py)

Provides the `GCM` class implementing AES-256-GCM. Its constructor takes
the master key `mk` and the metadata `time` (int), `edition` (int) and
`guid` (optional; required for items, omitted for channels).

Everything is derived deterministically at construction:

1. Common metadata `COMMON = TIME(5B) || EDITION(3B)`;
2. HKDF context `CTX = "CHCTX" || COMMON` (channel) or
   `"ITCTX" || GUID || COMMON` (item), deriving the sub-key
   `DEK = HKDF(mk, CTX)`;
3. GCM nonce `NONCE = TIME(6B) * 2`;
4. GCM associated data `AAD = "CHAAD" || COMMON` (channel) or
   `"ITAAD" || GUID || COMMON` (item).

Encryption (takes plaintext string `pt`):

1. Check the object is unused; raise `RuntimeError` otherwise (single-use,
   preventing nonce reuse);
2. Encrypt and digest, obtaining ciphertext and the authentication tag;
3. Return `TAG || CT`.

Decryption (takes `TAG || CT`):

1. Same single-use check;
2. Split `TAG` and `CT`, decrypt and verify the tag;
3. Raise `ValueError` on verification failure, else return the plaintext.
