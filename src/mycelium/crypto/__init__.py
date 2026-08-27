# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Publisher-side cryptographic configuration.

A single random 32-byte secret key (``SK``) seeds everything:

- the Ed25519 verification key ``VK`` is derived from ``SK``;
- the AES-256-GCM master key ``MK`` is *deterministically* derived from
  ``VK`` via PBKDF2 (password, salt and iteration count all taken from
  SHA-512 hashes of ``VK``);
- the cyclic-XOR pad ``PAD`` is *deterministically* derived from ``VK`` by
  concatenating the digests of the full SHA-2/SHA-3 family (see ``vk2pad``)
  and is used to obfuscate the protobuf wire format.

Subscribers therefore only need ``VK`` to both decrypt and verify, which
keeps key distribution down to a single short value.

Key-file storage
----------------

On disk, a publisher key is stored as a standard PKCS#8 PEM file (``.key``
by convention) instead of the legacy raw 32-byte payload (the old ``.dat``
convention). The PEM may optionally be passphrase-encrypted. See
``Config.export_pem`` / ``parse_pem`` for the in-memory format and
``save`` / ``load`` for atomic, permission-restricted file I/O; ``load``
auto-detects legacy raw-byte files so old keys migrate without loss.
"""

import os
import tempfile
from dataclasses import dataclass, field
from os import urandom
from uuid import UUID

from .AES import GCM
from .EdDSA import Signer, get_pub
from .Hash import (
    PBKDF2,
    SHA3_224,
    SHA3_256,
    SHA3_384,
    SHA3_512,
    SHA224,
    SHA256,
    SHA384,
    SHA512,
)

__all__ = [
    "Config",
    "new",
    "parse",
    "parse_pem",
    "save",
    "load",
    "vk2mk",
    "vk2pad",
    "xor",
]

# PBKDF2 iteration-count floor; the real count is ``100000 + PRN * 3``
# where PRN is derived from the verification key (varies per publisher).
_PBKDF2_MIN_ITERATIONS = 100000

# Digest order used by ``vk2pad``: SHA-2 then SHA-3, 224→512.
_PAD_ALGS = (
    SHA224,
    SHA256,
    SHA384,
    SHA512,
    SHA3_224,
    SHA3_256,
    SHA3_384,
    SHA3_512,
)


def vk2mk(vk: bytes) -> bytes:
    """
    Deterministically derive the 32-byte AES master key from a verification key.

    Steps:
    1. ``D1 = SHA512(VK)``;
    2. password = odd-indexed bytes of ``D1``, salt = even-indexed bytes;
    3. ``D2 = SHA512(D1)``; ``PRN`` = ``D2[31:33]`` (2 bytes at offset 31);
    4. iterations = ``100000 + PRN * 3``;
    5. ``MK = PBKDF2(password, salt, iterations)``.
    """
    d1 = SHA512(vk)
    d2 = SHA512(d1)
    pwd, salt = d1[::2], d1[1::2]
    prn = int.from_bytes(d2[31:33])
    cnt = _PBKDF2_MIN_ITERATIONS + prn * 3
    return PBKDF2(pwd, salt, cnt)


def vk2pad(vk: bytes) -> bytes:
    """
    Deterministically build the cyclic-XOR pad for a verification key.

    Following ``key = vk``, then for each algorithm in the SHA-2/SHA-3
    family (224→512), ``key += f(key)``:

        2-224, 2-256, 2-384, 2-512, 3-224, 3-256, 3-384, 3-512

    The result (376 bytes: 32 + 28+32+48+64 + 28+32+48+64) is used as the
    repeating keystream that obfuscates the protobuf wire format, so that
    a file host sees unrecognizable bytes instead of protobuf structure.
    """
    key = vk
    for f in _PAD_ALGS:
        key += f(key)
    return key


def xor(data: bytes, key: bytes) -> bytes:
    """
    Cyclic XOR of ``data`` with ``key`` (``key`` repeats if shorter).

    Self-inverse: ``xor(xor(data, key), key) == data``. Used both for the
    spore-link obfuscation (``mycelium.protocol.spore``) and for the protobuf
    wire obfuscation (``mycelium.protocol``). ``key`` must be non-empty.
    """
    return bytes([data[i] ^ key[i % len(key)] for i in range(len(data))])


@dataclass
class Config:
    """
    Publisher configuration: secret key, verification key, master key, pad.

    Args:
        sk: 32-byte Ed25519 secret key.

    The secret key and the derived master key are excluded from the repr
    on purpose (they must never leak into logs).
    """

    sk: bytes = field(repr=False)
    vk: bytes = field(init=False)
    _mk: bytes | None = field(init=False, default=None, repr=False)
    _pad: bytes | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self.vk = get_pub(self.sk)

    def __bytes__(self) -> bytes:
        """Serialize the configuration as the raw secret key (for storage)."""
        return self.sk

    @property
    def mk(self) -> bytes:
        """AES-256-GCM master key, derived lazily from ``vk`` and cached."""
        if self._mk is None:
            self._mk = vk2mk(self.vk)
        return self._mk

    @property
    def pad(self) -> bytes:
        """Cyclic-XOR pad for wire obfuscation, derived lazily from ``vk`` and cached."""
        if self._pad is None:
            self._pad = vk2pad(self.vk)
        return self._pad

    def gen_signer(self) -> Signer:
        """Create an Ed25519 signer from the secret key."""
        return Signer(self.sk)

    def gen_cipher(self, time: int, edition: int, guid: UUID | None = None) -> GCM:
        """Create a deterministic AES-GCM object for the given metadata."""
        return GCM(self.mk, time, edition, guid)

    def export_pem(self, passphrase: str | None = None) -> bytes:
        """
        Serialize this configuration to a standard PKCS#8 PEM file.

        Without ``passphrase`` the key is stored as plaintext PEM
        (``-----BEGIN PRIVATE KEY-----``); with it, the PEM is encrypted
        (``-----BEGIN ENCRYPTED PRIVATE KEY-----``,
        PBKDF2WithHMAC-SHA1AndAES128-CBC). PEM is the on-disk storage
        format for publisher keys — see ``mycelium.crypto.save`` /
        ``mycelium.crypto.load``.
        """
        from Crypto.PublicKey import ECC

        key = ECC.construct(curve="ed25519", seed=self.sk)
        if passphrase is None:
            return key.export_key(format="PEM").encode("utf-8")
        return key.export_key(
            format="PEM",
            passphrase=passphrase,
            protection="PBKDF2WithHMAC-SHA1AndAES128-CBC",
        ).encode("utf-8")


def new() -> Config:
    """Create a fresh configuration with a random 32-byte secret key."""
    return Config(urandom(32))


def parse(data: bytes) -> Config:
    """Rebuild a configuration from its serialized secret key (see ``bytes(Config)``)."""
    return Config(data)


def parse_pem(data: bytes, passphrase: str | None = None) -> Config:
    """
    Rebuild a configuration from a PKCS#8 PEM (see ``Config.export_pem``).

    Args:
        data: PEM bytes produced by ``Config.export_pem``, plain or
            passphrase-encrypted.
        passphrase: passphrase if ``data`` is encrypted.

    Raises:
        ValueError: malformed PEM, or the passphrase is missing/wrong.
    """
    from Crypto.PublicKey import ECC

    return Config(ECC.import_key(data, passphrase=passphrase).seed)


def save(
    path: str | os.PathLike[str],
    config: Config,
    passphrase: str | None = None,
) -> None:
    """
    Write ``config`` to ``path`` as a PKCS#8 PEM key file.

    The write is atomic (temp file in the same directory + ``os.replace``),
    and on POSIX the file is restricted to the owner (``0600``). With
    ``passphrase`` the PEM is encrypted; without it the key is stored as
    plaintext PEM. This is the on-disk replacement for the legacy raw-bytes
    key files (see ``load``).

    Args:
        path: destination file (``.key`` by convention).
        config: the publisher configuration to store.
        passphrase: optional passphrase that encrypts the PEM.
    """
    path = os.fspath(path)
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(
        dir=directory, prefix=os.path.basename(path) + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(config.export_pem(passphrase))
            f.flush()
            os.fsync(f.fileno())
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load(
    path: str | os.PathLike[str],
    passphrase: str | None = None,
) -> Config:
    """
    Read a publisher key file into a ``Config``.

    The preferred format is the PKCS#8 PEM written by ``save``; legacy
    raw 32-byte secret-key files (the old ``.dat`` convention) are
    auto-detected and still load, so existing keys migrate without loss.

    Args:
        path: key file to read.
        passphrase: passphrase if the PEM is encrypted.

    Raises:
        FileNotFoundError: ``path`` does not exist.
        ValueError: malformed PEM, or the passphrase is missing/wrong.
    """
    with open(os.fspath(path), "rb") as f:
        data = f.read()
    if data.startswith(b"-----BEGIN"):
        return parse_pem(data, passphrase)
    return Config(data)
