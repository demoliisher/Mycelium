# Picker Interface

The picker side of Mycelium: turn a spore link into a verified
plaintext sclerotium. In the ecosystem naming, the spore carries the
trail back to the sclerotium — `pull` follows it and harvests the fruit,
the feed content.

## Hypha

> Source: [hypha.py](../../../src/mycelium/interface/picker/hypha.py)

`Hypha.pull(link)` runs the whole subscription pipeline:

1. **Parse** the `mycelium://` spore link into host / path / verification
   key (`mycelium.protocol.parse`);
2. **Download** the feed blob over HTTPS from the spore (the hypha owns
   the download — `Spore` is a pure data class);
3. **Decrypt & verify** it with the spore's verification key
   (`Sclerotium.decrypt`), yielding a plaintext sclerotium.

The hypha is transport-agnostic: it only needs an HTTPS-accessible URL,
so any plain HTTP host works — not just Gitee.

Downloads are anonymous by default. For authenticated hosts (e.g. private
Git repositories) pass a pre-configured `requests.Session` carrying the
credentials; the session only carries credentials, never the spore link.

## Quick Start

```python
from mycelium.interface.picker import Hypha

sclerotium = Hypha().pull("mycelium://...")           # public spore, anonymous
sclerotium = Hypha(session=token_session).pull(link)  # private spore, token
```

## Notes

- A failed pull raises `ValueError` (invalid link, or decrypt/verify
  failure) or `ConnectionError` (spore unreachable).
- `pull` is the only way to fetch feed content in Mycelium. The sower
  side deliberately has no pull of its own (see `mycelium.interface.sower`).
