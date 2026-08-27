# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Sower-side storage contracts: push the feed blob into a hosting backend.

``Storage`` is the push-only abstract contract shared by every platform.
For git hosting platforms, ``GitPlatformClient`` refines it: a pure
abstract contract (defined here, like ``Storage`` itself) that declares the
lifecycle a git-host client must provide — namespace resolution, repo/fork
management, the contents write with its transient fork-race retry. Every
method is a ``pass`` placeholder and ``push`` is deliberately **not**
redefined: it stays abstract from ``Storage``, which keeps this class
abstract (it cannot be instantiated). Each platform module (``gitee``,
``gitcode``, ``github``) implements the full lifecycle itself, so a
platform client is self-contained.

Fetching (``pull``) is the picker's job (see
``mycelium.interface.picker``); a sower that wants to read back
what it pushed should go through the picker interface instead.
"""

from __future__ import annotations

import requests
from abc import ABC, abstractmethod

__all__ = ["Storage", "GitPlatformClient"]


class Storage(ABC):
    """Abstract file store for the sower: push-only."""

    @abstractmethod
    def push(self, path: str, data: bytes) -> None:
        """Create or overwrite ``path`` with ``data``."""
        pass


class GitPlatformClient(Storage):
    """
    Abstract contract shared by the git-hosting platform clients (sower side).

    Like ``Storage``, this class is a pure contract: every method below is
    an abstract ``pass`` placeholder and ``push`` is deliberately **not**
    redefined — it stays abstract from ``Storage``, which keeps this class
    abstract. Each platform module implements the full lifecycle itself:
    the constructor (``repo``/``fork`` mutual exclusion, lazy namespace
    cache), the class attributes (``BASE_URL``, ``default_branch``,
    ``_FORK_HOSTS``, ``_WRITE_RETRIES``, ``_WRITE_BACKOFF``) and every
    method declared below.

    Exactly one of ``repo`` / ``fork`` must be given (mutually exclusive):

    - ``repo`` mode: the target is ``<namespace>/repo`` (created when missing);
    - ``fork`` mode: the target is ``<namespace>/<source name>`` — the fork
      keeps the source's name, since the platform's fork API cannot rename.

    The namespace is resolved automatically from the authorized user's
    profile (``GET /user``) on first use and cached; there is no ``owner``
    parameter, so a mistyped owner is impossible.
    """

    BASE_URL = ""
    default_branch = "main"
    _FORK_HOSTS: tuple[str, ...] = ()
    _WRITE_RETRIES = 3
    _WRITE_BACKOFF = 2.0  # seconds

    @property
    @abstractmethod
    def base_url(self) -> str:
        """The API root of this platform."""
        pass

    @property
    @abstractmethod
    def namespace(self) -> str:
        """
        The authorized user's namespace, e.g. ``alice``.

        Fetched from the API profile (``GET /user``) on first use and
        cached; never taken from user input, so a mistyped owner is
        impossible.
        """
        pass

    @abstractmethod
    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Send a request with the access token attached; raise on non-2xx."""
        pass

    @abstractmethod
    def wait_ready(self, timeout: float | None = None) -> dict:
        """Block until this repository is visible to the API; return its info."""
        pass

    @classmethod
    @abstractmethod
    def _split_fork(cls, fork: str) -> tuple[str, str]:
        """
        Parse a fork source address into (owner, repo).

        Accepts "owner/repo", "owner/repo.git", a full URL
        ("https://<host>/owner/repo[.git]") and "<host>/owner/repo", where
        ``<host>`` is one of ``_FORK_HOSTS``.

        Raises:
            ValueError: malformed address, or a non-this-platform source
                (cross-platform forks are not supported yet).
        """
        pass

    @abstractmethod
    def ensure_repo_exists(self) -> bool:
        """
        Make sure the target repository exists; return True when it does.

        - repo mode: create ``<namespace>/repo`` when missing (existing -> no-op);
        - fork mode: reuse an existing same-named repository, otherwise fork
          the platform source under the same name.
        """
        pass

    @abstractmethod
    def create_repo(
        self, description: str | None = None, auto_init: bool = True
    ) -> dict:
        """
        Create a new repository and wait until it is visible to the API.

        With ``auto_init=True`` the repository is initialized with a README
        (first commit + default branch), which the contents API needs
        before the first file write.
        """
        pass

    @abstractmethod
    def fork_repo(self, fork: str, organization: str | None = None) -> dict:
        """
        Fork a same-platform repository into this account under its original name.

        The fork API does not support custom names, so the fork always keeps
        the source's name (the constructor already resolved the target to
        ``<namespace>/<source name>``). If the API reports a different path
        it is renamed defensively.
        """
        pass

    @abstractmethod
    def delete_repo(self) -> None:
        """Delete this repository (tests/cleanup only)."""
        pass

    @abstractmethod
    def _write_file(
        self, endpoint: str, payload: dict, sha: str | None
    ) -> requests.Response:
        """
        Send the create/update contents request.

        The strategy is platform-specific: Gitee and GitCode split POST
        (file missing) / PUT (file exists, sha required), while GitHub uses
        a single PUT for both.
        """
        pass

    @abstractmethod
    def _is_fork_race(self, exc: requests.exceptions.HTTPError) -> bool:
        """True if the error is this platform's transient fork race (retried by ``push``)."""
        pass

    @abstractmethod
    def _existing_sha(self, endpoint: str) -> str | None:
        """
        Return the file's current sha, or None if the file does not exist.

        A missing file is reported either as HTTP 404 (GitCode, GitHub) or
        as an empty list (Gitee); a non-empty list means the path is a
        directory.
        """
        pass

    # ``push`` is deliberately not redefined here: it stays abstract from
    # ``Storage``, which keeps this class abstract.
