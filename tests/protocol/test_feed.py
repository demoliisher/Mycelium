"""
Tests for the feed protocol: Fruit/Sclerotium encryption, decryption,
tamper detection, update semantics and the fruit encrypt cache.
"""

import unittest
from uuid import UUID, uuid4

from mycelium.crypto import new as new_config, vk2pad, xor
from mycelium.protocol import Fruit, Sclerotium
from mycelium.protocol import feed_pb as pb


class TestFeed(unittest.TestCase):
    def setUp(self):
        """Create a fresh cryptographic configuration for each test."""
        self.config = new_config()
        self.vk = self.config.vk

    # ---------- Fruit Tests ----------
    def test_fruit_roundtrip(self):
        """Encrypt and decrypt a Fruit, verify content and signature."""
        original = Fruit.new("Hello, world!")
        pbf = original.encrypt(self.config)

        decrypted = Fruit.decrypt(pbf, self.vk)
        self.assertEqual(original.guid, decrypted.guid)
        self.assertEqual(original.time, decrypted.time)
        self.assertEqual(original.edition, decrypted.edition)
        self.assertEqual(original.content, decrypted.content)

    def test_fruit_tampered_ciphertext(self):
        """Tampering with the ciphertext should cause decryption or signature failure."""
        fruit = Fruit.new("Secret")
        pbf = fruit.encrypt(self.config)

        # Corrupt the encrypted content (skip the first 16 bytes of tag)
        corrupted = pbf.content[:16] + b"\x00" + pbf.content[17:]
        pbf.content = corrupted

        with self.assertRaises(ValueError) as cm:
            Fruit.decrypt(pbf, self.vk)
        expected_error = "Failed to decrypt."
        self.assertEqual(expected_error, str(cm.exception))

    def test_fruit_tampered_signature(self):
        """Changing the signature should fail verification."""
        fruit = Fruit.new("Secret")
        pbf = fruit.encrypt(self.config)

        # Flip a byte in the signature
        corrupted_sign = pbf.sign[:32] + b"\xff" + pbf.sign[33:]
        pbf.sign = corrupted_sign

        with self.assertRaises(ValueError) as cm:
            Fruit.decrypt(pbf, self.vk)
        expected_error = f"Signature verification failed. GUID: {UUID(bytes=pbf.guid)}"
        self.assertEqual(expected_error, str(cm.exception))

    def test_fruit_update(self):
        """Update should increase edition and change content/time."""
        fruit = Fruit.new("Original")
        old_edition = fruit.edition
        old_time = fruit.time

        fruit.update("Updated")
        self.assertEqual(fruit.content, "Updated")
        self.assertEqual(fruit.edition, old_edition + 1)
        self.assertGreaterEqual(fruit.time, old_time)

    # ---------- Sclerotium Tests ----------
    def test_sclerotium_roundtrip(self):
        """Encrypt and decrypt a Sclerotium with multiple Fruits."""
        sclerotium = Sclerotium.new("Sclerotium title")
        sclerotium.entry("First post")
        sclerotium.entry("Second post")
        wire = sclerotium.encrypt(self.config)
        self.assertIsInstance(wire, bytes)  # wire format = obfuscated bytes
        decrypted = Sclerotium.decrypt(wire, self.vk)

        self.assertEqual(sclerotium.content, decrypted.content)
        self.assertEqual(sclerotium.time, decrypted.time)
        self.assertEqual(len(sclerotium), len(decrypted))

        for orig_fruit, dec_fruit in zip(sclerotium, decrypted):
            self.assertEqual(orig_fruit.guid, dec_fruit.guid)
            self.assertEqual(orig_fruit.time, dec_fruit.time)
            self.assertEqual(orig_fruit.edition, dec_fruit.edition)
            self.assertEqual(orig_fruit.content, dec_fruit.content)

    def test_sclerotium_wire_is_xor_obfuscated(self):
        """The wire bytes must differ from the raw protobuf and XOR back cleanly."""
        sclerotium = Sclerotium.new("Title")
        sclerotium.entry("Post")
        wire = sclerotium.encrypt(self.config)

        # Un-XOR with the pad and parse: must be a valid protobuf Sclerotium.
        raw = xor(wire, vk2pad(self.vk))
        msg = pb.Sclerotium.from_binary(raw)
        self.assertEqual(msg.fruits[0].guid, sclerotium.fruits[0].guid.bytes)

        # A random pad must NOT produce a parseable sclerotium.
        import secrets

        wrong = xor(wire, secrets.token_bytes(64))
        with self.assertRaises(ValueError):
            pb.Sclerotium.from_binary(wrong)

    def test_sclerotium_decrypt_accepts_raw_pb(self):
        """Sclerotium.decrypt still accepts a raw pb.Sclerotium (internal/tests use)."""
        sclerotium = Sclerotium.new("Title")
        sclerotium.entry("Post")
        raw = xor(sclerotium.encrypt(self.config), vk2pad(self.vk))
        msg = pb.Sclerotium.from_binary(raw)
        decrypted = Sclerotium.decrypt(msg, self.vk)
        self.assertEqual(decrypted.content, sclerotium.content)

    def test_sclerotium_tampered_signature(self):
        """Tampering with the wire must make decryption/verification fail."""
        sclerotium = Sclerotium.new("Title")
        sclerotium.entry("Post")
        wire = bytearray(sclerotium.encrypt(self.config))
        wire[len(wire) // 2] ^= 0xFF  # corrupt a byte inside the payload

        with self.assertRaises(ValueError):
            Sclerotium.decrypt(bytes(wire), self.vk)

    def test_sclerotium_tampered_fruit_signature(self):
        """Tampering with the wire (middle region) must make the sclerotium invalid."""
        sclerotium = Sclerotium.new("Title")
        sclerotium.entry("Post")
        wire = bytearray(sclerotium.encrypt(self.config))
        wire[len(wire) // 2] ^= 0xFF  # corrupt the ciphertext/signature region

        with self.assertRaises(ValueError):
            Sclerotium.decrypt(bytes(wire), self.vk)

    def test_sclerotium_update(self):
        """Sclerotium.update should change content and time without affecting fruits."""
        sclerotium = Sclerotium.new("Old title")
        sclerotium.entry("Post")
        old_time = sclerotium.time
        old_edition = sclerotium.edition

        sclerotium.update("New title")
        self.assertEqual(sclerotium.content, "New title")
        self.assertGreaterEqual(sclerotium.time, old_time)
        self.assertEqual(sclerotium.edition, old_edition + 1)
        self.assertEqual(len(sclerotium), 1)

    # ---------- Cache and Re-encryption Tests ----------
    def test_fruit_encrypt_cache_hit(self):
        """Encrypting the same fruit twice (without changes) should return identical ciphertext."""
        fruit = Fruit.new("Hello")
        pbf1 = fruit.encrypt(self.config)
        pbf2 = fruit.encrypt(self.config)
        self.assertEqual(pbf1.content, pbf2.content)  # ciphertext identical
        self.assertEqual(pbf1.sign, pbf2.sign)  # signature identical

    def test_fruit_encrypt_cache_invalidation_after_update(self):
        """After updating a fruit, cache should be invalid and new ciphertext differ."""
        fruit = Fruit.new("Old")
        pbf_old = fruit.encrypt(self.config)
        fruit.update("New")
        pbf_new = fruit.encrypt(self.config)
        self.assertNotEqual(pbf_old.content, pbf_new.content)
        self.assertNotEqual(pbf_old.sign, pbf_new.sign)

    def test_fruit_encrypt_with_different_edition_but_same_content(self):
        """
        If content unchanged but edition changes (e.g., by manual manipulation),
        encryption should produce different ciphertext because edition affects nonce/key.
        """
        fruit = Fruit.new("Content")
        pbf1 = fruit.encrypt(self.config)
        fruit.update()
        pbf2 = fruit.encrypt(self.config)
        self.assertNotEqual(pbf1.content, pbf2.content)

    # ---------- Exception Tests ----------
    def test_fruit_edition_zero_raises(self):
        with self.assertRaises(ValueError) as cm:
            Fruit(0, 0, "content", uuid4())
        self.assertEqual(str(cm.exception), "Edition must be a positive integer.")

    def test_sclerotium_edition_zero_raises(self):
        with self.assertRaises(ValueError) as cm:
            Sclerotium(0, 0, "content")
        self.assertEqual(str(cm.exception), "Edition must be a positive integer.")

    # ---------- Accessor Tests ----------
    def test_sclerotium_getitem_and_len(self):
        sclerotium = Sclerotium.new("Title")
        guid = sclerotium.entry("Post")
        self.assertEqual(len(sclerotium), 1)
        fruit = sclerotium[guid]
        self.assertEqual(fruit.guid, guid)
        self.assertEqual(fruit.content, "Post")

        with self.assertRaises(KeyError):
            _ = sclerotium[uuid4()]


if __name__ == "__main__":
    unittest.main()
