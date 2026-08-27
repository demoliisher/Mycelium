# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Cryptographic hash primitives used across Mycelium.

All primitives are thin, opinionated wrappers around the standard-library
``hashlib``/``hmac`` modules with fixed parameters:

- Hash (SHA-2):  SHA-224 / SHA-256 / SHA-384 / SHA-512
- Hash (SHA-3):  SHA3-224 / SHA3-256 / SHA3-384 / SHA3-512
- MAC:           HMAC-SHA-512
- KDF (PWD):     PBKDF2-HMAC-SHA-512 with a 32-byte output
- KDF (Key):     single-step HKDF built from nested HMAC-SHA-512, 32-byte output

The full SHA-2/SHA-3 family is used by ``mycelium.crypto.vk2pad`` to build
the cyclic-XOR keystream that obfuscates the protobuf wire format.
Fixing the algorithms and output lengths keeps the whole protocol
deterministic (no algorithm negotiation) and makes misuse harder.
"""

from hashlib import (
    pbkdf2_hmac,
    sha3_224,
    sha3_256,
    sha3_384,
    sha3_512,
    sha224,
    sha256,
    sha384,
    sha512,
)
from hmac import new

__all__ = [
    "SHA224",
    "SHA256",
    "SHA384",
    "SHA512",
    "SHA3_224",
    "SHA3_256",
    "SHA3_384",
    "SHA3_512",
    "HMAC",
    "PBKDF2",
    "HKDF",
]

# Domain separator for the HKDF construction (see ``HKDF``).
_DOMAIN = b"Mycelium"


def SHA224(data: bytes) -> bytes:
    """Return the raw SHA-224 digest of ``data`` (28 bytes)."""
    return sha224(data).digest()


def SHA256(data: bytes) -> bytes:
    """Return the raw SHA-256 digest of ``data`` (32 bytes)."""
    return sha256(data).digest()


def SHA384(data: bytes) -> bytes:
    """Return the raw SHA-384 digest of ``data`` (48 bytes)."""
    return sha384(data).digest()


def SHA512(data: bytes) -> bytes:
    """Return the raw SHA-512 digest of ``data`` (64 bytes)."""
    return sha512(data).digest()


def SHA3_224(data: bytes) -> bytes:
    """Return the raw SHA-3-224 digest of ``data`` (28 bytes)."""
    return sha3_224(data).digest()


def SHA3_256(data: bytes) -> bytes:
    """Return the raw SHA-3-256 digest of ``data`` (32 bytes)."""
    return sha3_256(data).digest()


def SHA3_384(data: bytes) -> bytes:
    """Return the raw SHA-3-384 digest of ``data`` (48 bytes)."""
    return sha3_384(data).digest()


def SHA3_512(data: bytes) -> bytes:
    """Return the raw SHA-3-512 digest of ``data`` (64 bytes)."""
    return sha3_512(data).digest()


def HMAC(key: bytes, msg: bytes) -> bytes:
    """Return the raw HMAC-SHA-512 digest of ``msg`` under ``key`` (64 bytes)."""
    return new(key, msg, sha512).digest()


def PBKDF2(pwd: bytes, salt: bytes, count: int) -> bytes:
    """
    Derive a 32-byte key from ``pwd``/``salt`` with PBKDF2-HMAC-SHA-512.

    Used to deterministically turn a public verification key into the
    AES master key (see ``mycelium.crypto.vk2mk``).
    """
    return pbkdf2_hmac("sha512", pwd, salt, count, 32)


def HKDF(ikm: bytes, ctx: bytes) -> bytes:
    """
    Derive a 32-byte sub-key from input keying material ``ikm`` and a context.

    Single-step HKDF built from nested HMAC-SHA-512:
    extract with the fixed domain separator as salt, then expand with a
    counter byte (``0x01``). The output is deterministic for a given
    ``(ikm, ctx)`` pair, which is exactly what the protocol requires for
    reproducible cipher parameters.
    """
    return HMAC(HMAC(_DOMAIN, ikm), ctx + b"\x01")[:32]
