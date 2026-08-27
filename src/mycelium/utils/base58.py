# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Base58 encoding/decoding and the custom 'fake64' serialization format.

Base58 (the Bitcoin alphabet) is compact and free of ambiguous characters
(0/O, l/I). ``fake64`` builds on it as a serialization scheme for flat
sequences and dicts: a list/tuple of byte strings (or a str→bytes dict)
is encoded into a single string by Base58-encoding each item and
separating items with characters that are *not* in the Base58 alphabet,
then optionally '='-padding the total length to a multiple of 4.

The disguise: the 58 Base58 characters plus the 6 separator characters
make up exactly the standard Base64 character set, so a fake64 string
looks like Base64 — a Base64 regex matches it — yet decoding it as Base64
yields garbage. Hence the name: it is a disguise, not Base64.
``mycelium.protocol.spore`` uses it to package spore links.
"""

import secrets

__all__ = [
    "b58encode",
    "b58decode",
    "fake64",
    "defake64",
]

# Bitcoin-style Base58 alphabet (no 0/O/I/l).
_ALPHABET: bytes = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
# Characters used as item separators. They are not part of the Base58
# alphabet, so an encoded item can never be confused with a separator.
_SEPARATORS: bytes = b"0OIl+/"
# Translation table mapping every separator byte to NUL, so ``defake64``
# can split on b"\x00" after a single translate call.
_TRANS_TABLE: bytes = bytes.maketrans(_SEPARATORS, bytes(len(_SEPARATORS)))


class InvalidCharacterError(ValueError):
    """Raised by ``b58decode`` when a character is outside the Base58 alphabet."""

    def __init__(self):
        message = "Invalid character in Base58 encoded string."
        super().__init__(message)


class EmptyItemError(Exception):
    """Raised by ``fake64`` when a sequence contains a falsy item (e.g. b'')."""

    def __init__(self):
        message = "List must not contain item(s) whose boolean value is False."
        super().__init__(message)


def b58encode(data: bytes) -> bytes:
    """
    Encode bytes to Bitcoin-style Base58.

    Args:
        data: input bytes.

    Returns:
        Base58-encoded bytes, with leading zero bytes represented as '1'
        characters; ``b''`` when the input is empty.
    """
    if not data:
        return b""

    leading_zeroes = len(data) - len(data.lstrip(b"\x00"))
    num = int.from_bytes(data, "big")

    chars = []
    while num:
        num, rem = divmod(num, 58)
        chars.append(_ALPHABET[rem : rem + 1])
    chars.reverse()

    return _ALPHABET[0:1] * leading_zeroes + b"".join(chars)


def b58decode(data: bytes) -> bytes:
    """
    Decode Base58-encoded bytes back to the original bytes.

    Args:
        data: Base58 data (may start with '1' characters for leading zeros).

    Returns:
        The decoded bytes; ``b''`` when the input is empty.

    Raises:
        InvalidCharacterError: if any character is not in the Base58 alphabet.
    """
    if not data:
        return b""

    leading_ones = len(data) - len(data.lstrip(_ALPHABET[0:1]))
    data_part = data[leading_ones:]

    num = 0
    for char in data_part:
        if (digit := _ALPHABET.find(char)) == -1:
            raise InvalidCharacterError()
        num = num * 58 + digit

    result = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    return b"\x00" * leading_ones + result


def fake64(
    data: list[bytes] | tuple[bytes] | dict[str, bytes], padding: bool = True
) -> bytes:
    """
    Serialize a collection of byte strings into a fake64 string.

    Sequences (list/tuple of bytes): each item is Base58-encoded and
    followed by a random separator chosen from ``_SEPARATORS``; the final
    trailing separator is stripped.

    Dicts (str keys → bytes values): the keys are UTF-8-encoded, then keys
    and values are serialized as two sequences joined by two separators,
    with a trailing separator left in place so ``defake64`` can tell the
    dict form apart from the sequence form.

    Padding: unless ``padding=False``, '=' characters are appended to make
    the total length a multiple of 4. This is NOT Base64.

    Disguise: the 58 Base58 characters and the 6 separator characters form
    exactly the standard Base64 character set, so the output is a valid
    Base64-looking string — a Base64 regex matches it — but decoding it as
    Base64 produces garbage. This is obfuscation for casual observers, not
    real Base64.

    Args:
        data: sequence of byte strings, or a dict with str keys and bytes
            values.
        padding: if True, pad with '=' to a multiple of 4. Default True.

    Returns:
        The fake64-encoded bytes.

    Raises:
        EmptyItemError: if a sequence contains a falsy item (e.g. b'').
        TypeError: if ``data`` is not a list, tuple or dict.
    """
    if not data:
        return b""

    if isinstance(data, list | tuple):
        if any(not item for item in data):
            raise EmptyItemError()
        encoded = b""
        for item in data:
            sep = bytes([secrets.choice(_SEPARATORS)])
            encoded += b58encode(item) + sep
        encoded = encoded.strip(_SEPARATORS)
    elif isinstance(data, dict):
        keys = list(k.encode("utf-8") for k in data.keys())
        values = list(data.values())
        sep1 = bytes([secrets.choice(_SEPARATORS)])
        sep2 = bytes([secrets.choice(_SEPARATORS)])
        # Leave the trailing separator for identification.
        encoded = fake64(keys, False) + sep1 + fake64(values, False) + sep2
    else:
        raise TypeError("Acceptable types: list, tuple, dict.")

    if padding:
        encoded += b"=" * (-len(encoded) % 4)
    return encoded


def defake64(data: bytes) -> list[bytes] | dict[str, bytes]:
    """
    Deserialize a fake64 string produced by ``fake64`` (its inverse).

    Strips the padding, maps separator bytes to NUL, splits on NUL and
    Base58-decodes each chunk. A trailing separator marks the dict form
    (an even number of chunks, first half = keys); anything else is the
    sequence form.

    Args:
        data: fake64-encoded bytes.

    Returns:
        A list of byte strings, or a dict of str→bytes for the dict form.

    Raises:
        ValueError: if a dict-form payload has an odd number of chunks.
    """
    if not data:
        return []

    data = data.rstrip(b"=")
    data = data.translate(_TRANS_TABLE)

    if b"\x00" not in data:
        return [b58decode(data)]

    parts = data.split(b"\x00")
    decoded_objects = [b58decode(part) for part in parts if part]

    if data.endswith(b"\x00"):  # Dict.
        if (length := len(decoded_objects)) % 2 == 0:
            center = length // 2
            keys = [k.decode("utf-8") for k in decoded_objects[:center]]
            values = decoded_objects[center:]
            return dict(zip(keys, values))
        else:
            raise ValueError("Invalid fake64.")
    else:  # Sequence.
        return decoded_objects
