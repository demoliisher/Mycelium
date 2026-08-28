# Core Module (Fruit / Sclerotium)

> Source: [core.py](../../src/mycelium/protocol/core.py)

## Data Structures

### Fruit

| Field       | Type       | Description                                     |
| ----------- | ---------- | ----------------------------------------------- |
| `time`      | `int`      | Last modification Unix timestamp (seconds).     |
| `edition`   | `int`      | Revision counter, starting at 1, +1 per update. |
| `content`   | `str`      | Plaintext content.                              |
| `guid`      | `UUID`     | UUIDv4 uniquely identifying the fruit.          |

**Encryption cache `_FruitCache`**: the protocol is deterministic — encrypting
an unchanged fruit twice must yield identical bytes. The cache is keyed by the
verification key `vk` and stores `(ciphertext, signature)`; it is dropped as a
whole as soon as the fruit's plaintext payload (guid/time/edition/content)
changes.

**Methods**:

- `cls.new(content)` — create a fruit with a fresh guid, the current
  timestamp and edition 1;
- `ins.update(value)` — replace the content, refresh the timestamp, bump the
  edition;
- `ins.encrypt(config)` — encrypt and sign with the given config (the
  signature covers guid, time, edition and content), returning a protobuf
  message;
- `cls.decrypt(msg, VK)` — decrypt and verify a protobuf `msg` with the
  verification key `VK`, returning a plaintext fruit; raises `ValueError` on
  failure.

### Sclerotium

| Field       | Type                 | Description                                 |
| ----------- | -------------------- | ------------------------------------------- |
| `time`      | `int`                | Last modification Unix timestamp (seconds). |
| `edition`   | `int`                | Revision counter, starting at 1.            |
| `content`   | `str`                | Plaintext sclerotium content (e.g. title).  |
| `fruits`    | `list[Fruit]`        | Fruits in reverse-chronological order.      |
| `_table`    | `dict[UUID, Fruit]`  | Fast guid→fruit lookup table.               |

**Methods**:

- `cls.new(content)` — create a sclerotium with the current timestamp and
  edition 1;
- `ins.entry(content)` — create and add a new fruit (internally `Fruit.new`),
  updating the sclerotium timestamp;
- `ins.update(value)` — replace the sclerotium content and bump the edition;
- `ins[guid]` — look up a fruit by guid;
- `ins.encrypt(config)` — encrypt the sclerotium content and sign it; the
  signature covers the sclerotium metadata and **the signature payloads of
  all fruits in order** (order binding);
- `cls.decrypt(msg, VK)` — decrypt and verify a protobuf message (bytes or
  message object), returning a plaintext sclerotium.

Note: every sclerotium encryption is treated as a fresh publication —
`encrypt` refreshes `time` to the current timestamp, so the nonce is never
reused (no caching here).

## Cryptography Workflow

All encryption and signing use a single `Config` object (publisher only, see
`mycelium.crypto`):

- **AES-256-GCM part**: `mk` — a 32-byte master key deterministically
  derived from the verification key `VK` via `vk2mk` (PBKDF2: password/salt
  taken from the odd/even bytes of `SHA512(VK)`, iteration count taken from
  `SHA512(SHA512(VK))`).
- **Ed25519 part**: `signer` — a signer built from the secret key `SK`;
  `vk` — the verification key.

Because `MK` is derived from `VK`, subscribers only need `VK` to both
decrypt (AES-GCM) and verify (Ed25519); key distribution shrinks to a single
value.

### Wire obfuscation

On top of protobuf serialization, the sclerotium bytes are obfuscated with a
cyclic XOR so a file host sees unrecognizable bytes instead of protobuf
structure. The repeating keystream (pad) is derived from `VK` alone
(`crypto.vk2pad`, exposed as `Config.pad`):

```python
    key = VK
    for f in [SHA-2 224/256/384/512, SHA-3 224/256/384/512]:
        key += f(key)          # hash of the accumulated key
```

The 376-byte result (32 + 28+32+48+64 + 28+32+48+64) is XORed cyclically
over the protobuf binary: `wire = XOR(protobuf, pad)`. Since `VK` is public,
this is obfuscation, not encryption — its purpose is hiding the protobuf
structure from the hosting platform and casual observers.

### Fruit workflow

Fruits and sclerotia share the same AES-GCM sub-key derivation (fully
deterministic, see `../../src/mycelium/crypto/AES.py`):

1. Inputs: `mk` (master key), `time`, `edition`, `guid` (sclerotia have no
   guid);
2. Common metadata `COMMON = TIME(5B) || EDITION(3B)`;
3. HKDF context: `CTX = "ITCTX" || GUID || COMMON` (fruit) or
   `"CHCTX" || COMMON` (sclerotium);
4. Sub-key `DEK = HKDF(mk, CTX)`;
5. GCM nonce: `NONCE = TIME(6B) * 2`;
6. Associated data: `AAD = "ITAAD" || GUID || COMMON` (fruit) or
   `"CHAAD" || COMMON` (sclerotium).

#### Encryption & Serialization

1. Derive the cipher object from the metadata above;
2. Encrypt `content`; the ciphertext layout is `TAG(16B) || CIPHERTEXT`;
3. Sign the plaintext payload with the signer
   (fruit: `GUID || TIME || EDITION || CONTENT`);
4. Assemble the protobuf message (`time`, `edition`, ciphertext, `guid`,
   signature).

Returns a protobuf message object.

#### Decryption & Verification

1. Derive the cipher object from the same metadata;
2. Decrypt the payload and obtain the plaintext content;
3. Rebuild the plaintext `Fruit`;
4. Verify the signature with `VK`; raise `ValueError` on failure.

Returns a plaintext `Fruit`.

### Sclerotium workflow

Sclerotia have no guid: the cipher object is derived from `mk` directly
(`CTX = "CHCTX" || TIME(5B) || EDITION(3B)`).

#### Encryption & Serialization (sclerotium)

1. Every encryption is a fresh publication: `time` is refreshed to the
   current timestamp;
2. Encrypt each fruit sequentially, in the order of `fruits`;
3. Signature payload = sclerotium metadata + all fruit signature payloads in
   order (prevents reordering);
4. Assemble the protobuf message (`time`, `edition`, sclerotium ciphertext,
   signature, fruit list);
5. Serialize the message to bytes and XOR them cyclically with the pad
   (see "Wire obfuscation").

Returns the obfuscated wire bytes (`Sclerotium.encrypt`).

#### Parsing & Verification

1. Reverse the XOR with the same pad and import the protobuf message;
2. Decrypt the sclerotium content;
3. Decrypt and verify each fruit in the same order;
4. Rebuild `fruits` and `_table`;
5. Verify the overall sclerotium signature; raise `ValueError` on failure.

If all checks pass, the sclerotium is considered authentic and untampered.

## Security Considerations

- **Master key secrecy**: the master key is derived with PBKDF2 at
  100,000–296,605 iterations to resist brute force.
- **Nonce uniqueness**: the GCM nonce is derived deterministically from
  `time`; it is safe as long as a `(time, edition)` pair is never reused.
  The protocol guarantees this by strictly incrementing `edition` on every
  update; sclerotium encryption refreshes `time` on every publication.
- **Signature binding**: the sclerotium signature covers the metadata and
  all fruit signatures, binding the whole content set and its order.
- **Single-key distribution**: `MK` is deterministically derived from `VK`,
  so subscribers only need the verification key to decrypt and verify.

## Proto Definitions

The protobuf layer lives in `../../src/mycelium/protocol/feed.proto`
(`feed_pb.py` is generated code next to it — do not edit by hand; import it
as `feed_pb as pb`). On the wire the serialized message is additionally
XOR-obfuscated with the pad (see "Wire obfuscation"):

```protobuf
message Fruit {
    bytes time = 1;      // int2bytes(Unix timestamp)
    bytes edition = 2;   // int2bytes(revision counter)
    bytes content = 3;   // TAG || ciphertext
    bytes guid = 4;      // 16-byte UUID
    bytes sign = 5;      // 64-byte Ed25519 signature
}

message Sclerotium {
    bytes time = 1;
    bytes edition = 2;
    bytes content = 3;   // TAG || ciphertext
    bytes sign = 4;      // 64-byte signature over metadata + all fruit signatures
    repeated Fruit fruits = 5;
}
```
