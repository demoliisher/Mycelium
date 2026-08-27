# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Tests for publisher key-file storage: PKCS#8 PEM round-trips, optional
passphrase encryption, atomic save and legacy raw-byte migration.
"""

import os
import shutil
import unittest

from mycelium import crypto

# Scratch space for key files. Deliberately a plain directory under the
# workspace: the sandboxed dev environment denies writes inside
# tempfile-managed directories (TemporaryDirectory/mkdtemp), so the tests
# manage their own directory instead of using the system temp area.
_SCRATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".keyfile_scratch")


class TestPemRoundtrip(unittest.TestCase):
    """Config.export_pem / crypto.parse_pem round-trips."""

    def setUp(self):
        self.cfg = crypto.new()

    def test_export_pem_plain(self):
        pem = self.cfg.export_pem()
        self.assertTrue(pem.startswith(b"-----BEGIN PRIVATE KEY-----"))
        self.assertEqual(crypto.parse_pem(pem).sk, self.cfg.sk)

    def test_export_pem_encrypted(self):
        pem = self.cfg.export_pem("pw123")
        self.assertTrue(pem.startswith(b"-----BEGIN ENCRYPTED PRIVATE KEY-----"))
        self.assertEqual(crypto.parse_pem(pem, "pw123").sk, self.cfg.sk)

    def test_wrong_passphrase_raises(self):
        pem = self.cfg.export_pem("pw123")
        with self.assertRaises(ValueError):
            crypto.parse_pem(pem, "wrong")

    def test_vk_consistent(self):
        """The derived verification key must survive the PEM round-trip."""
        self.assertEqual(crypto.parse_pem(self.cfg.export_pem()).vk, self.cfg.vk)


class TestSaveLoad(unittest.TestCase):
    """crypto.save / crypto.load file I/O."""

    def setUp(self):
        self.cfg = crypto.new()
        shutil.rmtree(_SCRATCH, ignore_errors=True)
        os.makedirs(_SCRATCH)
        self.path = os.path.join(_SCRATCH, "publisher.key")

    def tearDown(self):
        shutil.rmtree(_SCRATCH, ignore_errors=True)

    def test_save_load_roundtrip(self):
        crypto.save(self.path, self.cfg)
        self.assertEqual(crypto.load(self.path).sk, self.cfg.sk)

    def test_save_load_with_passphrase(self):
        crypto.save(self.path, self.cfg, "pw123")
        self.assertEqual(crypto.load(self.path, "pw123").sk, self.cfg.sk)

    def test_load_wrong_passphrase_raises(self):
        crypto.save(self.path, self.cfg, "pw123")
        with self.assertRaises(ValueError):
            crypto.load(self.path, "wrong")

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            crypto.load(os.path.join(_SCRATCH, "nope.key"))

    def test_legacy_raw_bytes_auto_detected(self):
        """The old raw 32-byte key-file convention must still load."""
        with open(self.path, "wb") as f:
            f.write(bytes(self.cfg))
        self.assertEqual(crypto.load(self.path).sk, self.cfg.sk)

    def test_overwrite_is_atomic_no_leftovers(self):
        crypto.save(self.path, self.cfg)
        other = crypto.new()
        crypto.save(self.path, other)
        self.assertEqual(crypto.load(self.path).sk, other.sk)
        leftovers = [n for n in os.listdir(_SCRATCH) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    @unittest.skipUnless(os.name == "posix", "POSIX permissions only")
    def test_posix_permission_0600(self):
        crypto.save(self.path, self.cfg)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
