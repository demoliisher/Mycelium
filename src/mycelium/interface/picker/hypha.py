# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Picker interface: pull a spore link and turn it into a verified plaintext channel.

Pipeline: parse the ``mycelium://`` spore link (the protocol header is
optional) → download the feed blob from the spore → decrypt and verify it
with the spore's verification key (``protocol.Sclerotium.decrypt``). The
hypha is transport-agnostic: it only needs an HTTPS-accessible URL, so
any plain HTTP host works — not just Gitee.

In the mycelium ecosystem naming, the picker is the mycelium itself:
a caught spore germinates, and the hypha — the picker's tool — follows
the spore's trail back to the host, where the sclerotium (the feed)
bears its fruit — the content the picker harvests.

Downloads are anonymous by default. A pre-configured ``requests.Session``
may be supplied for hosts that require authentication (e.g. private Git
repositories); the session only carries credentials, never the spore link.
"""

from __future__ import annotations

import requests

from mycelium.protocol import Sclerotium, Spore, parse as parse_spore

__all__ = ["Hypha"]


class Hypha:
    """
    Generic feed hypha (picker side).

    The hypha owns the download step: ``Spore`` is a pure data class that
    only generates/parses links, so fetching the feed blob happens here.

    Args:
        timeout: per-attempt download timeout in seconds.
        retries: download attempts before giving up.
        session: optional ``requests.Session`` for authenticated hosts
            (e.g. one that attaches an access token as a query parameter).
    """

    def __init__(
        self,
        timeout: float = 5,
        retries: int = 2,
        session: requests.Session | None = None,
    ):
        self.timeout = timeout
        self.retries = retries
        self.session = session

    def pull(self, link: str) -> Sclerotium:
        """
        Parse ``link``, download the feed and return the verified plaintext sclerotium.

        Raises:
            ValueError: invalid link or signature/authentication failure.
            ConnectionError: the spore is unreachable.
        """
        spore = parse_spore(link)
        data = self._download(spore)
        return Sclerotium.decrypt(data, spore.vk)

    def _download(self, spore: Spore) -> bytes:
        """
        Fetch the feed blob from the spore; raise ConnectionError when unreachable.
        """
        get = self.session.get if self.session is not None else requests.get
        url = f"https://{spore.host}/{spore.path}"
        for _ in range(self.retries):
            try:
                response = get(url, timeout=self.timeout)
                if response.status_code == 200:
                    return response.content
            except requests.RequestException:
                continue
        raise ConnectionError("Spore is not reachable")
