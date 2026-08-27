# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
AES-256-GCM with fully deterministic parameter derivation.

Instead of transmitting a fresh random nonce with every message, Mycelium
derives *everything* from the master key and public metadata:

- sub-key (DEK): ``HKDF(master_key, ctx)``
- nonce:         TIME (6 bytes) repeated twice
- AAD:           domain-separation label + metadata

As long as a ``(time, edition)`` pair is never reused, the nonce is never
reused and the confidentiality guarantees of AES-GCM hold. The protocol
enforces this by strictly incrementing ``edition`` on every update.

Every ``GCM`` object is single-use: a second encrypt/decrypt call raises
``RuntimeError``, making accidental nonce reuse impossible.
"""

from uuid import UUID

from Crypto.Cipher import AES

from .Hash import HKDF

__all__ = ["GCM"]

# ---- domain-separation labels -------------------------------------------
_CHANNEL_CTX = b"CHCTX"  # HKDF context prefix for channel content
_ITEM_CTX = b"ITCTX"  # HKDF context prefix for item content
_CHANNEL_AAD = b"CHAAD"  # GCM associated-data prefix for channel content
_ITEM_AAD = b"ITAAD"  # GCM associated-data prefix for item content

_TAG_LEN = 16  # AES-GCM authentication tag length in bytes


def _common_bytes(time: int, edition: int) -> bytes:
    """Serialize the shared metadata: TIME(5B) || EDITION(3B)."""
    return time.to_bytes(5) + edition.to_bytes(3)


def _gcm_nonce(time: int) -> bytes:
    """Deterministic 12-byte GCM nonce: TIME(6B) repeated twice."""
    return time.to_bytes(6) * 2


def _gcm_aad(time: int, edition: int, guid: UUID | None = None) -> bytes:
    """Associated data bound to the encrypted payload."""
    common = _common_bytes(time, edition)
    if guid is None:  # channel content
        return _CHANNEL_AAD + common
    return _ITEM_AAD + guid.bytes + common  # item content


def _hkdf_ctx(time: int, edition: int, guid: UUID | None = None) -> bytes:
    """HKDF context separating channels, items and metadata versions."""
    common = _common_bytes(time, edition)
    if guid is None:
        return _CHANNEL_CTX + common
    return _ITEM_CTX + guid.bytes + common


def _new_cipher(mk: bytes, time: int, edition: int, guid: UUID | None = None):
    """Build a fresh AES-GCM cipher with all parameters derived deterministically."""
    dek = HKDF(mk, _hkdf_ctx(time, edition, guid))
    nonce = _gcm_nonce(time)
    aad = _gcm_aad(time, edition, guid)
    cipher = AES.new(dek, AES.MODE_GCM, nonce)
    cipher.update(aad)
    return cipher


class GCM:
    """
    Single-use AES-256-GCM encryptor/decryptor with deterministic parameters.

    Args:
        mk: 32-byte AES master key.
        time: Unix timestamp (seconds) of the payload.
        edition: strictly increasing version counter.
        guid: item UUID; ``None`` for channel content.

    The ciphertext layout is ``TAG(16B) || CIPHERTEXT``.
    """

    def __init__(
        self, mk: bytes, time: int, edition: int, guid: UUID | None = None
    ):
        self._cipher = _new_cipher(mk, time, edition, guid)
        self._consumed = False

    def _consume(self) -> None:
        """Mark the object as used; raise if it was used before."""
        if self._consumed:
            raise RuntimeError("This GCM object has already been used.")
        self._consumed = True

    def encrypt(self, pt: str) -> bytes:
        """Encrypt ``pt`` and return ``TAG || CIPHERTEXT``."""
        self._consume()
        ct, tag = self._cipher.encrypt_and_digest(pt.encode("utf-8"))
        self._cipher = None
        return tag + ct

    def decrypt(self, cd: bytes) -> str:
        """Decrypt ``TAG || CIPHERTEXT``; raise ValueError on authentication failure."""
        self._consume()
        tag, ct = cd[:_TAG_LEN], cd[_TAG_LEN:]
        try:
            plain = self._cipher.decrypt_and_verify(ct, tag)
        except ValueError:
            raise ValueError("Failed to decrypt.") from None
        else:
            self._cipher = None
            return plain.decode("utf-8")
