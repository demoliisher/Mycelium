# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Small type and conversion helpers shared across Mycelium.

- ``timestamp``: current Unix time in whole seconds.
- ``int2bytes``: minimal big-endian byte serialization of an integer, used
  for the signed payloads and the protobuf wire format.
"""

from time import time

__all__ = ["timestamp", "int2bytes"]


def timestamp() -> int:
    """Return the current Unix timestamp in whole seconds."""
    return int(time())


def int2bytes(i: int) -> bytes:
    """
    Serialize a non-negative integer to its minimal big-endian byte form.

    ``0`` becomes ``b""`` (empty bytes), so an absent integer field on the
    wire decodes back to 0.
    """
    return i.to_bytes((i.bit_length() + 7) // 8)
