# Crypto Module

The cryptographic foundation of Mycelium: **everything except the
publisher's random signing secret key is derived deterministically** — the
verification key `VK` derives the AES master key and the wire-obfuscation
pad, so subscribers only need the tiny `VK` to decrypt content and
authenticate the publisher.

## Modules

- [Hash](Hash.md) — SHA-2/SHA-3 wrappers, HMAC, PBKDF2, HKDF; also the
  derivation details of `vk2mk` / `vk2pad`
- [AES](AES.md) — AES-256-GCM (single-use `GCM`)
- [EdDSA](EdDSA.md) — Ed25519 signer/verifier

## Config Object (`crypto.Config`)

> Source: `__init__.py`

The single user-facing entry point, constructed from the 32-byte signing
secret key `sk` (it derives `vk`, and lazily `mk` and `pad`):

- `crypto.new()` — a config with a random 32-byte secret key;
- `crypto.parse(data)` / `bytes(config)` — serialize/deserialize the secret
  key (in-memory / legacy format);
- `config.export_pem([passphrase])` / `crypto.parse_pem(data[, passphrase])`
  — standard PKCS#8 PEM round-trip;
- `crypto.save(path, config[, passphrase])` / `crypto.load(path[, passphrase])`
  — key files (see below);
- `config.gen_signer()` — an Ed25519 signer;
- `config.gen_cipher(time, edition[, guid])` — a deterministic AES-GCM
  object;
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

The parameters requiring uniqueness (the nonce) are guaranteed
non-repeating by the deterministic derivation — as long as a
`(time, edition)` pair is never reused. GCM objects are forcibly
single-use, ruling out misuse at the implementation level.
