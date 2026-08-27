"""
Tests for the mycelium.utils.typetools module.
"""

import unittest

from mycelium.utils.typetools import int2bytes, timestamp


class TestTimestamp(unittest.TestCase):
    """Tests for the timestamp helper."""

    def test_returns_int(self):
        self.assertIsInstance(timestamp(), int)

    def test_non_decreasing(self):
        a = timestamp()
        b = timestamp()
        self.assertGreaterEqual(b, a)


class TestInt2Bytes(unittest.TestCase):
    """Tests for minimal big-endian integer serialization."""

    def test_roundtrip(self):
        for i in (0, 1, 255, 256, 2**32, 2**64 - 1):
            self.assertEqual(int.from_bytes(int2bytes(i), "big"), i)

    def test_zero_is_empty(self):
        self.assertEqual(int2bytes(0), b"")

    def test_minimal_length(self):
        self.assertEqual(len(int2bytes(255)), 1)
        self.assertEqual(len(int2bytes(256)), 2)


if __name__ == "__main__":
    unittest.main()
