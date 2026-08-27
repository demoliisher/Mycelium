# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Utility package: shared low-level helpers.

- ``base58``: Base58 encoding plus the custom ``fake64`` serialization
  used for spore links. ``fake64`` covers flat sequences and dicts; its
  character set is exactly the standard Base64 one (58 encoding chars + 6
  separator chars), so the output looks like Base64 and matches a Base64
  regex, but decoding it as Base64 yields garbage.
- ``typetools``: timestamp and minimal big-endian integer serialization
  used by the protocol payloads.

Project scripts (e.g. the GFM table alignment tool) live in ``scripts/``
at the repository root, outside the package.
"""

__all__ = [
    "base58",
    "typetools",
]
