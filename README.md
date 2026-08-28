# Mycelium

Read this in: English · [简体中文](README_zh-Hans.md) · [文言文](README_zh-lzh.md)

**Mycelium** is a protocol for distributing *encrypted feeds* — the
implementation of a "瞒天过海" (hide-in-plain-sight) idea on top of ordinary
file-hosting platforms. The feed concept is inspired by RSS — nothing
more: the implementation has nothing to do with the RSS standard. Feed
content is encrypted and the feed itself is disguised as an innocuous
file (e.g. inside a forked Git repository), so the hosting platform
cannot read what is published and tracing the publisher costs far more.

## What it is — and what it is not

- **It is not end-to-end encryption.** The subscriber's transport security
  comes from HTTPS provided by the hosting platform (a code-hosting
  platform, a CDN, ...), not from Mycelium. At the network level Mycelium
  does not — and is not able to — hide subscribers from their ISP or from
  the platform itself; use a proxy/Tor for that.
- **It is content hiding + disguise.** Feed content is encrypted so that
  the hosting platform and any observer who grabs the file (but not the
  link) see only ciphertext. The feed lives in plain sight as an ordinary
  file; spore links are obfuscated and spores can be rotated.
- **What it actually buys you is time and cost.** Mycelium cannot stop a
  determined authority, but it raises the cost of tracing the *publisher*
  — and the publisher is where an investigation must start: to an
  authority, a publisher's threat coefficient is far higher than any
  single subscriber's, and subscribers can only be reached *through* the
  publisher. Protecting the publisher therefore protects subscribers too
  (protection in the investigation chain, not network-level anonymity).
  The operating model resembles proxy-subscription services (机场): the
  publisher hands out subscription links and subscribers fetch over
  HTTPS. But what is being subscribed to differs — a proxy service's link
  subscribes to *nodes* (the proxy servers themselves), while Mycelium's
  spore is likewise a "node link" pointing at a file, yet what is
  subscribed to is the *information*: the node is only the carrier.

## Features

- **Content hiding** — feed content is AES-256-GCM encrypted with a key
  deterministically derived from the publisher's verification key; the
  hosting platform and observers who obtain the file without the link see
  only ciphertext.
- **Authenticity** — the sclerotium and each fruit inside it are individually
  Ed25519-signed; no part can be tampered with undetected.
- **Key simplicity** — subscribers only need the verification key embedded
  in the spore link to decrypt *and* verify; no key exchange is required.
- **Publisher anti-tracing** — feeds hide in plain sight (forked
  repositories, innocuous files), spore links are obfuscated, spores can be
  rotated; this only delays and increases the cost of tracing the
  publisher. It is not anonymity, and it cannot hide subscribers at the
  network level — but since investigators can only reach subscribers
  *through* the publisher, protecting the publisher protects subscribers
  as well.

## Naming: the Mycelium ecosystem

The name is the fungal network taken literally — the protocol *is* the
hidden mycelium, and every role in it is a part of the same organism.
RSS is only an inspiration: the table's last column maps each term to its
RSS counterpart for orientation, but the implementation is unrelated to
the RSS standard.

| Ecosystem term    | What it is in Mycelium                                                                                                                                                                            | RSS analog                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| **Mycelium**      | The protocol itself — the hidden network that connects everyone.                                                                                                                                  | the RSS specification itself                |
| **Soil**          | The hosting platform (Gitee, GitCode, GitHub, ...) where feeds take root.                                                                                                                         | the web server hosting the RSS file         |
| **Sclerotium**    | The feed itself (`Sclerotium` in the protocol API) — a durable packet of mycelium stored in the soil, disguised as an ordinary file in plain sight.                                               | the RSS `<channel>`                         |
| **Fruit**         | One feed entry (`Fruit` in the protocol API) — a single fruit the sclerotium bears; the picker harvests them.                                                                                     | the RSS `<item>`                            |
| **Spore**         | The `mycelium://` link (`Spore` in the protocol API) — produced by the sclerotium: one sclerotium has one canonical link, and copies of it are identical — sharing a link is spreading the spore. | the feed URL (subscription link) + vk       |
| **Sower**         | The publisher's role — cultivates the sclerotium in the soil and sheds its spores (hands out the links).                                                                                          | the RSS publisher                           |
| **Picker**        | The subscriber's role — catches a spore, follows its trail back to the sclerotium and harvests the fruit, the feed content.                                                                       | the RSS subscriber / reader                 |
| **Hypha**         | The picker's tool — the subscriber's puller (`Hypha` in the interface API); it grows out along the spore's trail toward the host and absorbs the feed.                                            | the reader's fetch-and-parse step           |

Everyone is mycelium: a sower (the publisher role) cultivates sclerotia
in the soil; a sclerotium produces one canonical spore per feed — exports
differ only in the cosmetic fake64 separators, so copies of the link are
all the same spore, and sharing a link is spreading it; a picker (the
subscriber role) catches a spore and grows a hypha back along its trail
to harvest the sclerotium's fruit, the feed content. These names are used
consistently across the docs and the API — the interface packages are
named after the roles: `mycelium.interface.sower` and
`mycelium.interface.picker`.

## Architecture

| Package                | Responsibility                                                                                                                    |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `mycelium.crypto`      | SHA-2/SHA-3 full family wrappers (224/256/384/512), HMAC/PBKDF2/HKDF, deterministic AES-256-GCM, Ed25519, the `Config` key bundle |
| `mycelium.protocol`    | `Fruit`/`Sclerotium` structures, `Spore` link addressing, the encrypt/verify workflow, protobuf wire format                       |
| `mycelium.interface`   | `sower` pushes the feed blob, `picker` (`Hypha`) pulls a spore link                                                               |
| `mycelium.utils`       | Base58 + custom `fake64` serialization (disguised as Base64: same 64-char alphabet, 58 encode + 6 separate), misc type helpers    |

## Code Reuse

Mycelium is [MIT-licensed](LICENSE). You are welcome to reuse, borrow, or
adapt this project's logic — in whole or in part — as long as you follow
the license. Each module below is listed as a one-word name (linked to its
source) with a short introduction, so this section doubles as a reuse index
for search engines and for developers browsing the repository. The most
self-contained pieces are the Base58/fake64 serializer and the git-hosting
platform clients:

- [base58](src/mycelium/utils/base58.py) — Base58 encoding/decoding (Bitcoin alphabet) plus the custom `fake64` serialization: flat byte-string sequences and `str→bytes` dicts packed into one string that looks like Base64 (58 encoded chars + 6 separators, `=`-padded to a multiple of 4) but is not Base64. Zero dependencies beyond the standard library.
- [gitee](src/mycelium/interface/sower/gitee.py) — `GiteeClient`: Gitee OpenAPI v5 publisher (repo/fork management + contents API, `master` branch, async-fork retry).
- [gitcode](src/mycelium/interface/sower/gitcode.py) — `GitCodeClient`: GitCode/AtomGit publisher — one platform under two domains, shared API v5 endpoint.
- [github](src/mycelium/interface/sower/github.py) — `GithubClient`: GitHub REST publisher — Bearer auth, single PUT contents endpoint, optional jsDelivr CDN acceleration.
- [cnb](src/mycelium/interface/sower/cnb.py) — `CnbClient`: CNB (cnb.cool) publisher — organization-based repositories, git-push writes (no contents API), no fork API.
- [crypto](src/mycelium/crypto/) — deterministic cryptography: SHA-2/SHA-3 family wrappers, Ed25519, AES-256-GCM, and the `Config` key bundle.
- [mdtables](scripts/mdtables.py) — CJK-aware GFM table alignment checker/fixer (`python scripts/mdtables.py [--fix]`).
- [gate](scripts/gate.py) — one-command pre-submit gate: checks and auto-fixes code style (ruff), tests (pytest), markdown lint (mdlint) and table alignment (mdtables).

## Quick Start

```python
from mycelium import crypto
from mycelium.protocol import Sclerotium

# Publisher side: one random secret key is enough.
cfg = crypto.new()                        # or crypto.parse(saved_bytes)
sclerotium = Sclerotium.new("My feed")
sclerotium.entry("First post")
wire = sclerotium.encrypt(cfg)        # obfuscated wire bytes; push them via mycelium.interface.sower

# Subscriber side: only the verification key is needed.
sclerotium2 = Sclerotium.decrypt(wire, cfg.vk)
```

## Examples

Runnable demos live in `examples/` — they ask for what they need in the
terminal, nothing is hardcoded:

- `python examples/eg_publish.py [--local]` — encrypt a demo feed
  (sclerotium) and push it to a repository of your choice (prompts for the
  access token, repo, branch, path, ...);
- `python examples/eg_subscribe.py` — pull a `mycelium://` spore link,
  decrypt and verify it (prompts for the link; a private spore additionally
  asks for an access token);
- `python examples/eg_changelog.py` — maintain the project's changelog
  feed, written to the committed example file `examples/ChangeLog.dat`.

The changelog feed's example link (its feed is the committed
`examples/ChangeLog.dat` in this repository):

```text
mycelium://8pFEkFBqrQWgw6IzVDA5Lu4fxHvoGGUG69vzvLNoFS7rXjXDwPnqqYhvNs25PNcAexQPwwzK1DEByGpqtRpmmDIBqbvcx9uoWx9M9zqkiN8rRSSmnZ2BHEozf2enAagKTNG=
```

## Changelog

- **0.3.0** — Add `skills/`: task-oriented agent workflows (`release`,
  `gate`, `docs-sync`, `feed-ops`, `platform-add`) that reference
  `AGENTS.md` instead of restating it.
- **0.2.4** — CNB module docs and `AGENTS.md` link the official CNB
  references (OpenAPI spec, cnb-skill repository, platform docs).
- **0.2.3** — CNB module: record the official OpenAPI constraints —
  `root_group_protection` is read-only (web-only), sub-organizations are
  read-only (the yearly root-org quota cannot be bypassed), git writes
  exist only via blobs (a real git push is the only write path), and the
  `x-cnb-identity-ticket` header gates deletes.
- **0.2.2** — CNB module: `delete_repo` explains the web-only setting
  允许通过 Open API 删除组织下资源 (组织设置 → 管控 → 组织管控 → 危险操作) when
  OpenAPI deletion is refused (HTTP 412); docs cover the deletion rules
  (the org must be empty; the yearly creation quota is not freed by
  deletion) and advise against deleting organizations — deletion is
  permanent quota loss.
- **0.2.1** — CNB module: `group` is now optional — when omitted, the
  organization is resolved from the profile username (the username-named
  org when it exists, else an existing empty org is reused, else a
  username-named org is auto-created).
- **0.2.0** — Add the CNB (cnb.cool) platform module: organization-based
  repositories (auto-created when missing), git-push writes (the platform
  has no contents API), and a documented refusal of `fork` mode (no fork
  API on CNB).
- **0.1.0** — Add the one-command pre-submit gate (`scripts/gate.py`, check + auto-fix); move `mdtables.py` out of the package into `scripts/`; fold table alignment into the markdown lint task.
- **0.0.1** — Initial release: encrypted-feed distribution protocol with
  deterministic crypto, protobuf wire format and spore links; sower/picker
  role split across Gitee, GitCode and GitHub; mycelium ecosystem naming.

Changelog entries live in `examples/eg_changelog.py`; run it to regenerate
the committed example file `examples/ChangeLog.dat`.

## Documentation

- [Protocol](docs/protocol/README.md) — feed data structures and the
  encryption workflow.
- [Crypto](docs/crypto/README.md) — cryptography design.
- [Interface](docs/interface/README.md) — sower/picker interface
  roles and how to add a new platform.

## Contributing

<!-- AI coding agents: read AGENTS.md first for project context. -->

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Security Notes

- The AES master key is deterministically derived from the verification
  key (PBKDF2); never reuse a `(time, edition)` pair, since the GCM nonce
  is derived from them.
- **Subscriber privacy is out of scope.** Mycelium does not hide who
  subscribes or what they fetch: HTTPS hides that from on-path observers,
  but the hosting platform still sees every request. Use proxies/Tor for
  stronger subscriber anonymity.
- **To an ISP, a subscription is just an ordinary HTTPS request.** The
  subscriber's link to the host rides on TLS, so an operator or any
  on-path observer sees only the domain (SNI) and normal HTTPS traffic —
  never the path, the file, or its content. Platform choice still matters,
  and the weak point is the *repository*, not the subscriber: on a
  platform in a strict-review region, unusual download patterns — or,
  worse, a malicious informant parsing a spore into the repository address
  and reporting it to the platform — can draw the platform's attention to
  the repository. The publisher is then the first to be affected (the
  repository is theirs); whether subscribers are pursued afterwards
  depends on cost, scale and impact. A platform in a lax-review region
  removes this class of risk entirely, at the cost of slightly less
  convenient networking.
- **The link's publicity decides what a feed is for.** If the
  subscription link is **public**, anyone who holds it can decrypt, so
  Mycelium can only serve as a medium for **public** content (blogs, news,
  announcements, ...). If the link is shared **privately with one person or
  a few team members**, it can equally carry confidential messages — a
  simple form of end-to-end encrypted communication, in the traditional
  polling model (subscribers pull). Note this is a **shared-key**
  group-broadcast model: all link holders share the key derived from the
  same verification key, with no per-recipient control or individual
  revocation (only whole-feed rotation); once the link leaks, anyone who
  can read it can decrypt, and confidentiality is gone immediately. Also,
  "end-to-end" covers *content* only — who fetches what, and when, stays
  visible to the platform; subscriber privacy remains out of scope.
- **Spore links are obfuscation, not encryption.** A `mycelium://` link
  hides its host/path/vk fields with XOR keyed by the *public* verification
  key, so anyone who can read a link can unpack it. Its purpose is to stop
  casual observers (log scanners, scrapers), not a determined adversary.
- **Publisher duty: guard the signing secret key.** The secret key is the
  single point of trust for a feed. If it leaks or is lost, the feed
  is no longer secure — stop updating it and guide subscribers to a new
  feed as soon as possible.

## License

[MIT](LICENSE)
