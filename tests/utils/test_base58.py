# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Unit tests for the mycelium.utils.base58 module.
"""

import itertools
import secrets
import unittest
from unittest.mock import patch

from mycelium.utils.base58 import (
    _SEPARATORS,
    EmptyItemError,
    InvalidCharacterError,
    b58decode,
    b58encode,
    defake64,
    fake64,
)


class TestB58EncodeDecode(unittest.TestCase):
    """Tests for Base58 encoding and decoding."""

    def test_encode_empty(self):
        self.assertEqual(b58encode(b""), b"")

    def test_decode_empty(self):
        self.assertEqual(b58decode(b""), b"")

    def test_encode_decode_roundtrip(self):
        test_cases = [
            b"hello",
            b"world",
            b"\x00\x01\x02",
            b"\xff" * 10,
            b"1234567890",
        ]
        for original in test_cases:
            encoded = b58encode(original)
            decoded = b58decode(encoded)
            self.assertEqual(decoded, original)

    def test_leading_zero_bytes(self):
        data = b"\x00\x00\xff"
        encoded = b58encode(data)
        self.assertTrue(encoded.startswith(b"11"))
        decoded = b58decode(encoded)
        self.assertEqual(decoded, data)

        data = b"\x00\x00\x00"
        encoded = b58encode(data)
        self.assertEqual(encoded, b"111")
        decoded = b58decode(encoded)
        self.assertEqual(decoded, data)

    def test_decode_invalid_character(self):
        with self.assertRaises(InvalidCharacterError):
            b58decode(b"1234567890")
        with self.assertRaises(InvalidCharacterError):
            b58decode(b"1I23")

    def test_known_vectors(self):
        self.assertEqual(b58encode(b"\x00"), b"1")
        self.assertEqual(b58decode(b"1"), b"\x00")
        data = bytes.fromhex("61")
        encoded = b58encode(data)
        decoded = b58decode(encoded)
        self.assertEqual(decoded, data)


class TestFake64(unittest.TestCase):
    """Tests for fake64 serialization and defake64 deserialization."""

    def setUp(self):
        # Patch secrets.choice to return a deterministic sequence of ASCII codes
        ascii_codes = [ord(c) for c in _SEPARATORS.decode()]
        self.sep_cycle = itertools.cycle(ascii_codes)
        self.patcher = patch.object(secrets, "choice", side_effect=self.sep_cycle)
        self.mock_choice = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_fake64_list_roundtrip(self):
        items = [b"hello", b"world", b"\x00\x01"]
        encoded = fake64(items, padding=True)
        decoded = defake64(encoded)
        self.assertEqual(decoded, items)

        encoded_no_pad = fake64(items, padding=False)
        self.assertNotIn(b"=", encoded_no_pad)
        decoded_no_pad = defake64(encoded_no_pad)
        self.assertEqual(decoded_no_pad, items)

    def test_fake64_tuple_roundtrip(self):
        items = (b"a", b"bc", b"def")
        encoded = fake64(items)
        decoded = defake64(encoded)
        self.assertEqual(decoded, list(items))

    def test_fake64_dict_roundtrip(self):
        d = {"key1": b"value1", "key2": b"value2"}
        encoded = fake64(d, padding=True)
        decoded = defake64(encoded)
        self.assertEqual(decoded, d)

        encoded_no_pad = fake64(d, padding=False)
        decoded_no_pad = defake64(encoded_no_pad)
        self.assertEqual(decoded_no_pad, d)

    def test_fake64_empty_containers(self):
        self.assertEqual(fake64([]), b"")
        self.assertEqual(defake64(b""), [])

        self.assertEqual(fake64(()), b"")
        self.assertEqual(defake64(b""), [])

        self.assertEqual(fake64({}), b"")
        self.assertEqual(defake64(b""), [])

    def test_fake64_empty_item_raises(self):
        with self.assertRaises(EmptyItemError):
            fake64([b"valid", b""])
        with self.assertRaises(EmptyItemError):
            fake64([b"valid", None])

    def test_fake64_invalid_type_raises(self):
        with self.assertRaises(TypeError):
            fake64("not a sequence or dict")  # type: ignore
        with self.assertRaises(TypeError):
            fake64(123)  # type: ignore

    def test_defake64_single_part_no_separator(self):
        data = b58encode(b"hello")
        decoded = defake64(data)
        self.assertEqual(decoded, [b"hello"])

    def test_defake64_with_padding_and_trailing_separator(self):
        d = {"k": b"v"}
        encoded = fake64(d, padding=True)
        # Padding is no longer mandatory (the length may already be a
        # multiple of 4), so decoding must work either way.
        decoded = defake64(encoded)
        self.assertEqual(decoded, d)
        # If padding is present, the total length must be a multiple of 4.
        if encoded.endswith(b"="):
            self.assertEqual(len(encoded) % 4, 0)

    def test_defake64_invalid_dict_odd_parts(self):
        sep = _SEPARATORS[0:1]  # b'0'
        # Build a dict-style block with an odd number of chunks.
        parts = [
            b58encode(b"key1"),
            b58encode(b"val1"),
            b58encode(b"key2"),
        ]
        malformed = sep.join(parts) + sep  # trailing separator -> dict mode, odd chunks
        with self.assertRaises(ValueError):
            defake64(malformed)

    def test_defake64_with_consecutive_separators(self):
        # Build valid data with two consecutive separators.
        data = b58encode(b"hello") + b"0" + b"0" + b58encode(b"world")
        decoded = defake64(data)  # no trailing separator -> list
        self.assertEqual(decoded, [b"hello", b"world"])

    def test_fake64_deterministic_output_with_patch(self):
        items = [b"a", b"b"]
        encoded = fake64(items, padding=False)
        decoded = defake64(encoded)
        self.assertEqual(decoded, items)


if __name__ == "__main__":
    unittest.main()
