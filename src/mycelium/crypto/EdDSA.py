# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Ed25519 digital signatures (RFC 8032) on top of pycryptodome.

- ``Signer`` signs payloads with a 32-byte secret key.
- ``Verifier`` verifies signatures against the corresponding public key.
- ``get_pub`` derives the 32-byte public key from a secret key.
"""

from __future__ import annotations

from Crypto.Signature import eddsa

__all__ = ["Signer", "Verifier", "get_pub"]


class Signer:
    """Ed25519 signer bound to a 32-byte secret key."""

    def __init__(self, sk: bytes):
        self._sk = sk
        self._eks = eddsa.import_private_key(sk)
        self._eds = eddsa.new(self._eks, mode="rfc8032")

    def sign(self, data: bytes) -> bytes:
        """Sign ``data`` and return a 64-byte signature."""
        return self._eds.sign(data)


class Verifier:
    """Ed25519 verifier bound to a 32-byte public key."""

    def __init__(self, vk: bytes):
        self._vk = vk
        self._ekv = eddsa.import_public_key(vk)
        self._edv = eddsa.new(self._ekv, mode="rfc8032")

    def verify(self, data: bytes, sign: bytes) -> bool:
        """Return True iff ``sign`` is a valid signature of ``data``."""
        try:
            self._edv.verify(data, sign)
            return True
        except ValueError:
            return False


def get_pub(sk: bytes) -> bytes:
    """Derive the 32-byte Ed25519 public key for secret key ``sk``."""
    eks = eddsa.import_private_key(sk)
    ekv = eks.public_key()
    return ekv.export_key(format="raw")
