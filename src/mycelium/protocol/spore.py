# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Spore addressing model: a feed location hidden inside an opaque link.

A ``Spore`` bundles everything a subscriber needs — host, path and the
publisher's verification key — and can be exported to a compact link with
a custom ``mycelium://`` protocol header (the header is optional when
parsing: a bare payload is accepted too). The payload is XOR-obfuscated
and serialized with ``fake64`` so the fields are not directly readable;
note this is lightweight obfuscation (keyed by the public ``vk``), not
encryption.

In the mycelium ecosystem naming, the spore is produced by the
sclerotium — the feed — and carries its address: one sclerotium has
exactly one canonical link, and exports differ only in the cosmetic
fake64 separators, so copies of the link are all the same spore and
sharing a link is spreading the spore. A picker that catches one follows
its trail back to the host. ``Spore`` is a pure data class: it only
generates and parses spore links. Fetching the feed blob is the picker's
job — see ``mycelium.interface.picker.Hypha``.
"""

from __future__ import annotations

from dataclasses import dataclass

from mycelium.crypto import xor
from mycelium.utils.base58 import defake64, fake64

# Custom protocol header of spore links, e.g. "mycelium://<fake64 payload>".
_PREFIX = "mycelium://"


@dataclass
class Spore:
    """A feed spore: where the feed blob lives and which key verifies it."""

    host: str
    path: str
    vk: bytes

    def export(self) -> str:
        """Serialize the spore into a ``mycelium://`` link."""
        ct_host = xor(self.host.encode("utf-8"), self.vk)
        ct_path = xor(self.path.encode("utf-8"), ct_host)
        ct_vk = xor(self.vk, b"Mycelium")
        return _PREFIX + fake64([ct_host, ct_path, ct_vk]).decode("ascii")


def parse(link: str) -> Spore:
    """
    Parse a spore link back into a ``Spore``.

    The ``mycelium://`` protocol header is optional: a bare payload is
    parsed the same way.
    """
    if link.startswith(_PREFIX):
        link = link.removeprefix(_PREFIX)
    ct_host, ct_path, ct_vk = defake64(link.encode("ascii"))
    vk = xor(ct_vk, b"Mycelium")
    host = xor(ct_host, vk).decode("utf-8")
    path = xor(ct_path, ct_host).decode("utf-8")
    return Spore(host, path, vk)
