---
name: mycelium-feed-ops
description: Operate Mycelium feeds — publish/subscribe with the examples, PEM key handling, spore-link verification rules (never compare export strings).
---

# mycelium-feed-ops

Daily feed operations: publishing a feed (sower side), subscribing
(picker side), and maintaining the changelog feed. Use the examples as
the working tools; the rules below prevent the classic mistakes.

Rules of record: `AGENTS.md` (crypto/protocol architecture) and the
module docs under `docs/`.

## The three examples

- `examples/eg_publish.py` — publish/subscribe round-trip demo for one
  sower + one picker (read it to see the full workflow).
- `examples/eg_subscribe.py` — picker side: pull a feed from a spore
  link.
- `examples/eg_changelog.py` — maintains `examples/ChangeLog.dat`, the
  project's own changelog feed (regenerate with
  `uv run python examples/eg_changelog.py`).

## Key rules

1. **Keys are PEM.** Sowers keep keys as PKCS#8 PEM
   (`Config.export_pem`, passphrase optional). Legacy raw-byte `.dat`
   keys are migration-only — never reintroduce them as a storage format.
2. **Never compare exported spore strings.** `Spore.export()` picks
   cosmetic fake64 separators at random — two exports of the same link
   differ. Compare parsed fields (`Spore.parse`) or verify end-to-end
   with `Hypha.pull` instead; tests must never assert on export strings.
3. **Verification needs only `vk`.** The public verification key inside
   the spore link verifies *and* decrypts; pickers never need the secret
   key.
4. **Tokens are runtime-only.** Access tokens arrive via argv or the
   gitignored `tests/interface/tokens.py` — never in source, docs or
   fixtures.
5. **`(time, edition)` must never repeat** and GCM objects are
   single-use — never reuse a crypto object across encryptions.
