# Protocol Module

The feed data structures and the encryption workflow of the Mycelium
protocol: two plaintext classes encrypted and signed with a single
`Config`, serialized to an obfuscated protobuf wire format, and addressed
by a `mycelium://` spore link.

## Modules

- [core](core.md) — the `Fruit` / `Sclerotium` data structures, their
  encryption workflow and the protobuf wire format
- [spore](spore.md) — the `mycelium://` spore link addressing

## Overview

The protocol layer defines two plaintext classes (stored unencrypted), with
fields mirroring the Protocol Buffer messages (see `core.md`):

- **Fruit** — a single content entry (in the ecosystem naming, one fruit the
  sclerotium bears), e.g. a blog post or news article.
- **Sclerotium** — a collection of fruits published as one feed, e.g. a
  publication or topic channel. In the ecosystem naming the feed message is
  the sclerotium itself (the durable packet growing on the soil), and a
  picker follows a spore's trail back to it to harvest the fruit.
