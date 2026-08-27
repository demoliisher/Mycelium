"""
Tests for the picker hypha: spore-link parsing, download and the
decrypt/verify pipeline (the download step is mocked).
"""

import unittest
from unittest import mock

from mycelium.crypto import new as new_config
from mycelium.protocol import Sclerotium, Spore
from mycelium.interface.picker import Hypha


class TestHypha(unittest.TestCase):
    def setUp(self):
        self.cfg = new_config()
        self.spore = Spore("example.com", "feeds/feed.dat", self.cfg.vk)
        self.link = self.spore.export()

        self.sclerotium = Sclerotium.new("Hypha Test")
        self.sclerotium.entry("first")
        self.sclerotium.entry("second")
        self.wire = self.sclerotium.encrypt(self.cfg)

    def test_pull_roundtrip(self):
        """Parse link, download (mocked) and decrypt+verify to the same sclerotium."""
        with mock.patch.object(Hypha, "_download", return_value=self.wire) as dl:
            result = Hypha().pull(self.link)

        dl.assert_called_once()
        self.assertEqual(result.content, self.sclerotium.content)
        self.assertEqual(len(result), len(self.sclerotium))
        for orig, dec in zip(self.sclerotium, result):
            self.assertEqual(orig.guid, dec.guid)
            self.assertEqual(orig.content, dec.content)

    def test_pull_invalid_link_raises(self):
        with self.assertRaises(ValueError):
            Hypha().pull("https://not-a-spore-link")

    def test_pull_tampered_data_raises(self):
        """A corrupted feed blob must fail signature verification."""
        corrupted = self.wire[:-1] + bytes([self.wire[-1] ^ 0xFF])
        with mock.patch.object(Hypha, "_download", return_value=corrupted):
            with self.assertRaises(ValueError):
                Hypha().pull(self.link)

    def test_pull_unreachable_raises(self):
        with mock.patch.object(
            Hypha, "_download", side_effect=ConnectionError("unreachable")
        ):
            with self.assertRaises(ConnectionError):
                Hypha().pull(self.link)

    def test_pull_passes_session(self):
        """The optional session must be used by the download step."""
        session = mock.Mock()
        session.get.return_value = mock.Mock(status_code=200, content=self.wire)
        result = Hypha(session=session).pull(self.link)
        session.get.assert_called_once()
        self.assertEqual(result.content, self.sclerotium.content)

    def test_parse_spore_roundtrip(self):
        """The spore link must survive an export/parse round trip."""
        from mycelium.protocol import parse as parse_spore

        parsed = parse_spore(self.link)
        self.assertEqual(parsed.host, self.spore.host)
        self.assertEqual(parsed.path, self.spore.path)
        self.assertEqual(parsed.vk, self.spore.vk)

    def test_parse_without_protocol_header(self):
        """A link without the ``mycelium://`` header must parse the same way."""
        from mycelium.protocol import parse as parse_spore

        bare = self.link.removeprefix("mycelium://")
        parsed = parse_spore(bare)
        self.assertEqual(parsed.host, self.spore.host)
        self.assertEqual(parsed.path, self.spore.path)
        self.assertEqual(parsed.vk, self.spore.vk)

    def test_spore_equality_across_export_variants(self):
        """Different fake64 separator variants decode to equal spores."""
        from mycelium.protocol import parse as parse_spore

        variant = self.spore.export()  # random separators -> different string
        self.assertEqual(parse_spore(variant), self.spore)
        self.assertEqual(parse_spore(self.link), parse_spore(variant))
        self.assertNotEqual(
            parse_spore(self.link), Spore("other.com", "x", self.cfg.vk)
        )


if __name__ == "__main__":
    unittest.main()
