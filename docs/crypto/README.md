# Crypto Module

This module is the cryptographic foundation of Mycelium. Its design follows
a deliberately radical idea: **everything except the publisher's random
signing secret key is derived deterministically**. For example, the
verification key `VK` derived from the secret key is used both for
signature verification and for deriving the encryption master key —
subscribers only need the tiny `VK` to decrypt content and authenticate
the publisher.

## Hash Module

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

The full SHA-2/SHA-3 family feeds `vk2pad` (see "Config Object" below).

## AES Module

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

## EdDSA Module

> Source: [EdDSA.py](../../src/mycelium/crypto/EdDSA.py)

- `Signer(sk)` — signer bound to a 32-byte secret key; `sign(data)`
  produces a 64-byte Ed25519 signature.
- `Verifier(vk)` — verifier bound to a 32-byte public key;
  `verify(data, sign)` returns a boolean.
- `get_pub(sk)` — derives the public key from a secret key.

## Config Object (`crypto.Config`)

> Source: `__init__.py`

All user-facing key material is managed by this object. Its constructor
takes a single argument — the 32-byte signing secret key `sk` — and
derives the verification key `vk`.

The master key `mk` (used for AES-256-GCM) is computed lazily and cached to
avoid repeated PBKDF2 work. The derivation (`vk2mk`):

1. `D1 = SHA512(VK)`;
2. password = odd-indexed bytes of `D1`, salt = even-indexed bytes;
3. `D2 = SHA512(D1)`; `PRN = D2[31:33]` (2 bytes at offset 31) as an integer;
4. iteration count `CNT = 100000 + PRN * 3` (range 100,000–296,605);
5. `MK = PBKDF2(PWD, SALT, CNT)`.

The cyclic-XOR pad (used to obfuscate the protobuf wire format, see
`mycelium.protocol`) is also derived from `VK` (`vk2pad`, exposed as the
lazy `Config.pad` property): starting from `key = VK`, append the digest
of the accumulated key for every SHA-2/SHA-3 algorithm in order
(2-224, 2-256, 2-384, 2-512, 3-224, 3-256, 3-384, 3-512), yielding a
376-byte keystream. `crypto.xor(data, key)` applies that keystream
cyclically; it is self-inverse.

Usage:

- `crypto.new()` — create a configuration with a random 32-byte secret key;
- `crypto.parse(data)` / `bytes(config)` — serialize/deserialize the secret
  key (in-memory / legacy format);
- `config.export_pem([passphrase])` — export a standard PKCS#8 PEM
  (encrypted when a passphrase is given);
- `crypto.parse_pem(data[, passphrase])` — rebuild a configuration from a
  PEM;
- `crypto.save(path, config[, passphrase])` — atomically write `config` to
  a PEM key file (`0600` on POSIX);
- `crypto.load(path[, passphrase])` — read a key file (legacy raw-byte
  files are auto-detected and migrate cleanly);
- `config.gen_signer()` — create an Ed25519 signer;
- `config.gen_cipher(time, edition[, guid])` — create a deterministic
  AES-GCM object;
- `config.pad` / `crypto.vk2pad(vk)` — the wire-obfuscation keystream;
- `crypto.xor(data, key)` — cyclic XOR (self-inverse).

### Key-File Storage

On disk, a publisher signing key is stored as a standard **PKCS#8 PEM**
file (`.key` by convention), replacing the legacy raw-32-byte `.dat`
convention:

- **Standard format**: `-----BEGIN PRIVATE KEY-----`, readable and
  convertible by tools like openssl; with a `passphrase` the export is
  `-----BEGIN ENCRYPTED PRIVATE KEY-----` (PBKDF2 + AES-128-CBC), so the
  key never sits on disk in plaintext;
- **Atomic write & permissions**: `save` writes a temp file in the same
  directory and `os.replace`s it (no torn files), then `chmod 0600` on
  POSIX so only the owner can read it;
- **Smooth migration**: `load` auto-detects PEM vs. the legacy raw-byte
  format — old `publisher.dat`/`config.dat` files load as-is, and one
  `save` call rewrites them as PEM;
- **Passphrase source is the caller's choice**: `save`/`load` only take an
  explicit `passphrase` argument; the example scripts read it from the
  `MYCELIUM_KEY_PASSPHRASE` environment variable (real deployments may use
  an interactive prompt or an OS keyring instead).

Security note: `Config.__repr__` excludes the secret key and the master
key, so they can never leak into logs.

## Security Considerations

Although most parameters are deterministically derived, the parameters that
require uniqueness (the nonce) are guaranteed non-repeating by the
derivation — as long as a `(time, edition)` pair is never reused. GCM
objects are forcibly single-use, ruling out misuse at the implementation
level.

A word of caution: Mycelium is only a protocol for encrypted **feeds**, and
the publicity of the link decides what a channel is for — with a **public**
link, publish only **public** content that is merely blocked on the network
(blogs, news, announcements); with a link shared **privately with one
person or a few team members**, it may equally carry confidential messages
(a shared-key group broadcast, polled by subscribers; the secret is gone
the moment the link leaks, and there is no per-recipient revocation).
