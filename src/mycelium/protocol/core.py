# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Mycelium feed data structures and their encryption workflow.

``Fruit`` is a single content entry — one fruit the sclerotium bears
(a blog post, a news article, ...); a ``Sclerotium`` is a collection of
fruits published as one feed. In the mycelium ecosystem naming, the feed
message is the sclerotium and each entry is a fruit: the sclerotium
produces the spore link, and a picker follows the spore's trail back to
the sclerotium to harvest the fruit.

Both expose the same lifecycle:

- ``new`` / ``entry`` / ``update`` mutate the plaintext object;
- ``encrypt(cfg)`` encrypts (AES-256-GCM) and signs (Ed25519) the content
  and returns the *wire format*: the protobuf binary, further obfuscated
  with a cyclic XOR keyed by the pad derived from the verification key
  (``crypto.vk2pad`` / ``Config.pad``) so a file host sees unrecognizable
  bytes instead of protobuf structure;
- ``decrypt(data, vk)`` reverses the XOR, parses the protobuf message,
  verifies the signatures and decrypts the content back into a plaintext
  object. The AES master key is derived from ``vk`` (``crypto.vk2mk``), so
  subscribers only need the publisher's verification key to read a feed.

The protobuf layer is defined in ``feed.proto`` next to this module
(generated into ``pb``).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from json import dumps
from typing import Any
from uuid import UUID, uuid4

from mycelium.crypto import Config, vk2mk, vk2pad, xor

from ..crypto.AES import GCM
from ..crypto.EdDSA import Verifier
from ..utils.typetools import int2bytes, timestamp
from . import feed_pb as pb


@dataclass(eq=False)
class _FruitCache:
    """
    Per-publisher cache of a fruit's (ciphertext, signature) pair.

    Encrypting the same unchanged fruit twice must yield identical bytes
    (the protocol is deterministic), so the result is cached per
    verification key. The cache is dropped as soon as the fruit's
    plaintext payload (guid, time, edition, content) changes.
    """

    fruit: Fruit
    _cached_payload: bytes = field(init=False, repr=False)
    _data: dict[bytes, tuple[bytes, bytes]] = field(
        init=False, repr=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        self.refresh()

    @property
    def payload(self) -> bytes:
        return self.fruit.payload

    def __getitem__(self, vk: bytes) -> tuple[bytes, bytes] | None:
        if self._cached_payload != self.payload:
            self.refresh()
        return self._data.get(vk, (None, None))

    def __setitem__(self, vk: bytes, value: tuple[bytes, bytes]) -> None:
        if self._cached_payload != self.payload:
            self.refresh()
        self._data[vk] = value

    def refresh(self) -> None:
        """Drop all cached results; call after the fruit's plaintext changes."""
        self._cached_payload = self.payload
        self._data.clear()


@dataclass
class Fruit:
    """
    A single feed entry — one fruit the sclerotium bears.

    Attributes:
        time: last modification Unix timestamp (seconds).
        edition: revision counter, starting at 1 and strictly increasing.
        content: plaintext content.
        guid: UUIDv4 uniquely identifying the fruit.
    """

    time: int
    edition: int
    content: str
    guid: UUID
    cache: _FruitCache = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.edition <= 0:
            raise ValueError("Edition must be a positive integer.")
        self.cache = _FruitCache(self)

    @classmethod
    def new(cls, content: str) -> Fruit:
        """Create a fruit with the current timestamp and edition 1."""
        return cls(
            time=timestamp(),
            edition=1,
            content=content,
            guid=uuid4(),
        )

    @property
    def payload(self) -> bytes:
        """Plaintext bytes covered by the signature: GUID || TIME || EDITION || CONTENT."""
        return b"".join(
            [
                self.guid.bytes,
                int2bytes(self.time),
                int2bytes(self.edition),
                self.content.encode("utf-8"),
            ]
        )

    @classmethod
    def decrypt(cls, msg: pb.Fruit, vk: bytes, mk: bytes | None = None) -> Fruit:
        """
        Decrypt and verify a protobuf ``Fruit``.

        Args:
            msg: serialized fruit message.
            vk: publisher's Ed25519 verification key.
            mk: optional pre-derived AES master key (derived from ``vk`` if omitted).

        Raises:
            ValueError: authentication or signature verification failed.
        """
        if mk is None:
            mk = vk2mk(vk)

        time = int.from_bytes(msg.time)
        edition = int.from_bytes(msg.edition)
        cd = msg.content
        guid = UUID(bytes=msg.guid)

        cipher = GCM(mk, time, edition, guid)
        pt = cipher.decrypt(cd)
        fruit = cls(time, edition, pt, guid)

        if not Verifier(vk).verify(fruit.payload, msg.sign):
            raise ValueError(f"Signature verification failed. GUID: {fruit.guid}")

        fruit.cache[vk] = (cd, msg.sign)
        return fruit

    def encrypt(self, cfg: Config) -> pb.Fruit:
        """
        Encrypt and sign this fruit into a protobuf message.

        The result is cached per verification key, so re-encrypting an
        unchanged fruit returns byte-identical output.
        """
        cached_cd, cached_sig = self.cache[cfg.vk]
        if cached_cd is not None and cached_sig is not None:
            cd = cached_cd
            sig = cached_sig
        else:
            cipher = cfg.gen_cipher(self.time, self.edition, self.guid)
            signer = cfg.gen_signer()
            cd = cipher.encrypt(self.content)
            sig = signer.sign(self.payload)
            self.cache[cfg.vk] = (cd, sig)

        msg = pb.Fruit(
            time=int2bytes(self.time),
            edition=int2bytes(self.edition),
            content=cd,
            guid=self.guid.bytes,
            sign=sig,
        )
        return msg

    def update(self, value: str = "") -> None:
        """Replace the content, refresh the timestamp and bump the edition."""
        self.time = timestamp()
        self.edition += 1
        self.content = value
        self.cache.refresh()


@dataclass
class Sclerotium:
    """
    A feed sclerotium: metadata plus an ordered list of fruits.

    Attributes:
        time: last modification Unix timestamp (seconds).
        edition: revision counter, starting at 1.
        content: plaintext sclerotium content (e.g. a title or description).
        fruits: fruits in reverse-chronological creation order.
    """

    time: int
    edition: int
    content: str
    fruits: list[Fruit] = field(init=False, default_factory=list)
    _table: dict[UUID, Fruit] = field(init=False, default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.edition <= 0:
            raise ValueError("Edition must be a positive integer.")

    @classmethod
    def new(cls, content: str) -> Sclerotium:
        """Create a sclerotium with the current timestamp and edition 1."""
        return cls(
            time=timestamp(),
            edition=1,
            content=content,
        )

    @property
    def payload(self) -> bytes:
        """Plaintext bytes covered by the signature: metadata + all fruit payloads in order."""
        return b"".join(
            [
                int2bytes(self.time),
                int2bytes(self.edition),
                self.content.encode("utf-8"),
            ]
            + [fruit.payload for fruit in self.fruits]
        )

    def __iter__(self) -> Iterator[Fruit]:
        return iter(self.fruits)

    def __getitem__(self, guid: UUID) -> Fruit:
        return self._table[guid]

    def __len__(self) -> int:
        return len(self.fruits)

    @classmethod
    def decrypt(
        cls, msg: pb.Sclerotium | bytes, vk: bytes, mk: bytes | None = None
    ) -> Sclerotium:
        """
        Parse, decrypt and verify a sclerotium from wire bytes or a protobuf message.

        Args:
            msg: the wire format — XOR-obfuscated protobuf bytes produced by
                ``encrypt`` — or a raw ``pb.Sclerotium`` (e.g. from tests).
            vk: publisher's Ed25519 verification key.
            mk: optional pre-derived AES master key (derived from ``vk`` if omitted).

        Raises:
            ValueError: wire de-obfuscation, sclerotium content authentication,
                fruit signature or sclerotium signature verification failed.
        """
        if mk is None:
            mk = vk2mk(vk)

        if isinstance(msg, bytes):
            # Reverse the cyclic-XOR wire obfuscation, then parse protobuf.
            msg = pb.Sclerotium.from_binary(xor(msg, vk2pad(vk)))

        time = int.from_bytes(msg.time)
        edition = int.from_bytes(msg.edition)
        cd = msg.content

        cipher = GCM(mk, time, edition)
        pt = cipher.decrypt(cd)
        sclerotium = cls(time, edition, pt)

        for pbf in msg.fruits:
            fruit = Fruit.decrypt(pbf, vk, mk)
            sclerotium.fruits.append(fruit)
            sclerotium._table[fruit.guid] = fruit

        if not Verifier(vk).verify(sclerotium.payload, msg.sign):
            raise ValueError("Sclerotium signature verification failed.")

        return sclerotium

    def encrypt(self, cfg: Config) -> bytes:
        """
        Encrypt and sign the sclerotium (and every fruit), returning the wire format.

        The protobuf binary is additionally obfuscated with a cyclic XOR
        keyed by ``cfg.pad`` (derived from the verification key), so the
        hosted file is not recognizable as protobuf.

        Every encryption is treated as a fresh publication: ``time`` is
        refreshed to the current timestamp, so a nonce is never reused
        (fruit-level caching does not apply here).
        """
        # A unique time per encryption makes caching useless: whatever the
        # previous `time` was, the current timestamp is used every time.
        self.time = timestamp()

        cipher = cfg.gen_cipher(self.time, self.edition)
        signer = cfg.gen_signer()
        cd = cipher.encrypt(self.content)
        sn = signer.sign(self.payload)

        msg = pb.Sclerotium(
            time=int2bytes(self.time),
            edition=int2bytes(self.edition),
            content=cd,
            sign=sn,
        )

        for fruit in self.fruits:
            msg.fruits.append(fruit.encrypt(cfg))
        return xor(msg.to_binary(), cfg.pad)

    def update(self, value: str) -> None:
        """Replace the sclerotium content, refresh the timestamp and bump the edition."""
        self.time = timestamp()
        self.edition += 1
        self.content = value

    def entry(self, content: str) -> UUID:
        """Create a new fruit, prepend it to the sclerotium and return its guid."""
        fruit = Fruit.new(content)
        self.time = fruit.time
        self.fruits.insert(0, fruit)
        self._table[fruit.guid] = fruit
        return fruit.guid


def preview(obj: Fruit | Sclerotium, rc: bool = False) -> dict[str, Any] | None:
    """
    Pretty-print (or return) a human-readable preview of a sclerotium or fruit.

    Args:
        obj: the sclerotium or fruit to preview.
        rc: if True, return the preview dict instead of printing it.

    Returns:
        The preview dict when ``rc`` is True, otherwise None.
    """
    dt = datetime.fromtimestamp(obj.time)
    table = {
        "Time": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "Content": obj.content,
    }
    if isinstance(obj, Fruit):
        table["GUID"] = str(obj.guid)
        table["Edition"] = obj.edition
    elif isinstance(obj, Sclerotium):
        table["Fruits"] = [preview(fruit, rc=True) for fruit in obj.fruits]
    else:
        raise TypeError("obj must be a Sclerotium or Fruit.")

    if rc:
        return table
    else:
        print(dumps(table, ensure_ascii=False, indent=2))
