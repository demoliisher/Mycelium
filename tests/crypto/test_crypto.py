"""
Tests for the crypto primitives: deterministic AES-GCM, Ed25519 signing,
cyclic XOR and the vk-derived pad.
"""

import unittest
from os import urandom

from mycelium.crypto import new as new_config, vk2pad, xor
from mycelium.crypto.AES import GCM
from mycelium.crypto.EdDSA import Signer, Verifier, get_pub
from mycelium.crypto.Hash import SHA224, SHA256, SHA3_512
from mycelium.utils.typetools import timestamp

_TEST_STR = "Mycelium"
_TEST_DATA = _TEST_STR.encode("utf-8")


class TestGCM(unittest.TestCase):
    def setUp(self):
        self.mk = urandom(32)
        self.time = timestamp()
        self.edition = 1

    def test_aesgcm_basic(self):
        c1 = GCM(self.mk, self.time, self.edition)
        cipher = c1.encrypt(_TEST_STR)
        c2 = GCM(self.mk, self.time, self.edition)
        decrypted = c2.decrypt(cipher)
        self.assertEqual(_TEST_STR, decrypted)

    def test_aesgcm_different_edition(self):
        c1 = GCM(self.mk, self.time, 1)
        c2 = GCM(self.mk, self.time, 2)
        c1 = c1.encrypt(_TEST_STR)
        c2 = c2.encrypt(_TEST_STR)
        self.assertNotEqual(c1, c2)

    def test_aesgcm_used_twice(self):
        c1 = GCM(self.mk, self.time, self.edition)
        ct = c1.encrypt(_TEST_STR)
        with self.assertRaises(RuntimeError):
            c1.encrypt("Other")
        with self.assertRaises(RuntimeError):
            c1.decrypt(ct)

        c2 = GCM(self.mk, self.time, self.edition)
        pt = c2.decrypt(ct)
        with self.assertRaises(RuntimeError):
            c2.decrypt(ct)
        with self.assertRaises(RuntimeError):
            c2.encrypt(pt)


class TestEd25519(unittest.TestCase):
    def test_signer_verifier(self):
        sk = urandom(32)
        signer = Signer(sk)
        sign = signer.sign(_TEST_DATA)
        verifier = Verifier(get_pub(sk))
        self.assertTrue(verifier.verify(_TEST_DATA, sign))
        self.assertFalse(verifier.verify(_TEST_DATA[::-1], sign))


class TestXor(unittest.TestCase):
    """Tests for the cyclic XOR helper."""

    def test_roundtrip(self):
        data = b"hello world"
        key = b"secret"
        self.assertEqual(xor(xor(data, key), key), data)

    def test_cyclic_for_longer_data(self):
        data = b"A" * 100
        key = b"key"
        out = xor(data, key)
        # The key must repeat: every 3 bytes the pattern cycles.
        self.assertEqual(out[:3], out[3:6])
        self.assertEqual(out[3:6], out[6:9])

    def test_self_inverse_empty_data(self):
        self.assertEqual(xor(b"", b"k"), b"")

    def test_spore_link_uses_shared_xor(self):
        # spore.py previously had its own _xor; the shared one must agree.
        from mycelium.protocol import Spore, parse as parse_spore

        spore = Spore("gitee.com", "a/b", b"v" * 32)
        parsed = parse_spore(spore.export())
        self.assertEqual(
            (parsed.host, parsed.path, parsed.vk),
            (spore.host, spore.path, spore.vk),
        )


class TestVk2Pad(unittest.TestCase):
    """Tests for the vk→pad keystream derivation."""

    def test_deterministic(self):
        vk = urandom(32)
        self.assertEqual(vk2pad(vk), vk2pad(vk))

    def test_length(self):
        vk = urandom(32)
        # 32 + 28+32+48+64 (SHA-2) + 28+32+48+64 (SHA-3) = 376
        self.assertEqual(len(vk2pad(vk)), 376)

    def test_cascade_structure(self):
        vk = urandom(32)
        pad = vk2pad(vk)
        self.assertEqual(pad[:32], vk)
        self.assertEqual(pad[32:60], SHA224(vk))
        self.assertEqual(pad[60:92], SHA256(vk + SHA224(vk)))
        self.assertEqual(pad[-64:], SHA3_512(pad[:-64]))

    def test_different_vk_different_pad(self):
        self.assertNotEqual(vk2pad(urandom(32)), vk2pad(urandom(32)))

    def test_config_pad_property(self):
        cfg = new_config()
        self.assertEqual(cfg.pad, vk2pad(cfg.vk))
        # Lazy + cached: same object identity after the first access.
        self.assertIs(cfg.pad, cfg.pad)


if __name__ == "__main__":
    unittest.main()
