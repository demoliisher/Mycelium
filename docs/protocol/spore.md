# Spore

> Source: [spore.py](../../src/mycelium/protocol/spore.py)

A `Spore` bundles everything a subscriber needs — host, path and the
publisher's verification key — and can be exported to a compact link with a
custom `mycelium://` protocol header (the header is optional when parsing: a
bare payload is accepted too). The payload is XOR-obfuscated and serialized
with `fake64` (Base58 with 6 separator chars, disguised as Base64) so the
fields are not directly readable; note this is lightweight obfuscation
(keyed by the public `vk`), not encryption.

In the mycelium ecosystem naming, the spore is produced by the sclerotium —
the feed — and carries its address: one sclerotium has exactly one canonical
link, and exports differ only in the cosmetic fake64 separators, so copies
of the link are all the same spore and sharing a link is spreading the
spore. A picker that catches one follows its trail back to the host.
`Spore` is a pure data class: it only generates and parses spore links.
Fetching the feed blob is the picker's job — see
`mycelium.interface.picker.Hypha`.

- `Spore(host, path, vk)` — a pure data class;
- `spore.export()` — serialize into a `mycelium://` link;
- `protocol.parse(link)` — parse back into a `Spore` (the `mycelium://`
  header is optional).
