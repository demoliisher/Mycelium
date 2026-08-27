# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
GitHub platform module (sower side): push the encrypted feed into a GitHub repository.

The client is bound to exactly one target, chosen by two **mutually
exclusive** constructor arguments:

- ``repo`` — manage ``<owner>/repo``: create it when missing, then push
  into it (``owner`` is the account login, resolved automatically from
  the authorized user's profile — there is no ``owner`` parameter);
- ``fork`` — disguise mode: fork a *GitHub* source repository into this
  account under the **same name**. If a same-named repository already
  exists in the account (e.g. from an earlier fork), it is reused instead
  of forking again.

Cross-platform sources (Gitee, GitCode, ...) are **not** supported yet:
the GitHub API cannot import them, so such fork links are rejected with a
hint to import the repository manually on the GitHub web UI.

GitHub materializes forks asynchronously: a write issued right after
forking can transiently fail while the default branch is still being
initialized; ``push`` retries such errors briefly.

The feed blob is written through ``push`` via the contents API. Pulling it
back is picker behavior — use ``mycelium.interface.picker``
(``Hypha``) for that.

**CDN acceleration.** Subscribers fetch the feed blob over plain HTTPS
from the spore host. For GitHub, that host is normally
``raw.githubusercontent.com``, which can be slow or blocked in some
regions. The ``cdn`` constructor argument accepts a ``bool`` or a
callable: ``True`` selects the default jsDelivr mirror (``_jsdelivr_cdn``,
the ``cdn.jsdelivr.net/gh`` mirror), a callable rewrites raw
``githubusercontent.com`` URLs with its own mirror, and ``False`` (the
default) keeps raw links. Note that jsDelivr serves *public* repositories
only — for a private repository keep the default ``cdn=False`` (the
subscriber then needs an authenticated session).

To avoid polluting the open-source community, **never send pull requests
to upstream repositories** — a forked copy is a disguise container, not a
contribution.

The access token is **not** embedded in this module; it is always passed
explicitly as the ``access_token`` constructor argument (or ``sys.argv[1]``
in the ``__main__`` demo). GitHub authenticates via the ``Authorization:
Bearer`` header (unlike Gitee/GitCode, which use an ``access_token`` query
parameter).
"""

from __future__ import annotations

import base64
import sys
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import requests

from mycelium.protocol import Spore

from .base import GitPlatformClient

__all__ = ["GithubClient", "_jsdelivr_cdn"]

# Fine-grained personal access token: see the sower README. Metadata
# (read-only) is mandatory and auto-added; Administration and Contents
# read/write are what Mycelium's sower needs.


def _jsdelivr_cdn(url: str) -> str:
    """
    Rewrite a raw.githubusercontent.com URL to its jsDelivr CDN mirror.

    ``https://raw.githubusercontent.com/OWNER/REPO/BRANCH/PATH``
    becomes ``https://cdn.jsdelivr.net/gh/OWNER/REPO@BRANCH/PATH``.

    Any other URL (e.g. an API endpoint) is returned unchanged. jsDelivr
    mirrors *public* repositories only; private repositories keep the
    default ``cdn=False`` instead.
    """
    prefix = "https://raw.githubusercontent.com/"
    if not url.startswith(prefix):
        return url
    rest = url[len(prefix):]
    owner, repo, branch, path = rest.split("/", 3)
    return f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{path}"


class GithubClient(GitPlatformClient):
    """
    GitHub REST API client bound to a single repository (sower side).

    Exactly one of ``repo`` / ``fork`` must be given (mutually exclusive):

    - ``repo`` mode: the target is ``<login>/repo`` (created when missing);
    - ``fork`` mode: the target is ``<login>/<source name>`` — the fork
      keeps the source's name, since the GitHub fork API cannot rename.

    The account login (``namespace``) is resolved automatically from the
    authorized user's profile (``GET /user``) on first use and cached; there
    is no ``owner`` parameter, so a mistyped owner is impossible.

    ``cdn`` accepts a ``bool`` or a callable that rewrites raw
    ``githubusercontent.com`` URLs into accelerated mirrors: ``True``
    selects the default jsDelivr mirror (see ``_jsdelivr_cdn``), a callable
    is used as-is, and ``False`` (the default) keeps plain raw links
    (required for private repos).
    """

    BASE_URL = "https://api.github.com"
    _FORK_HOSTS = ("github.com",)

    def __init__(
        self,
        access_token: str,
        repo: str | None = None,
        fork: str | None = None,
        branch: str | None = None,
        cdn: Callable[[str], str] | bool = False,
        poll_interval: float = 1.0,
        max_poll: int = 30,
    ):
        if (repo is None) == (fork is None):
            raise ValueError(
                "exactly one of repo/fork must be given "
                "(they are mutually exclusive)"
            )
        self.access_token = access_token
        self.fork = fork
        if fork is not None:
            # Fork mode: the target keeps the source's name.
            self.repo = self._split_fork(fork)[1]
        else:
            assert repo is not None
            self.repo = repo
        self.branch = branch or self.default_branch
        self.poll_interval = poll_interval
        self.max_poll = max_poll
        self.session = requests.Session()
        self._namespace: str | None = None  # lazy cache of the account login
        if cdn is True:
            cdn = _jsdelivr_cdn
        elif cdn is False:
            cdn = None
        elif not callable(cdn):
            raise TypeError("cdn must be a bool or a callable")
        self.cdn = cdn

    @property
    def base_url(self) -> str:
        """The API root of this platform."""
        return self.BASE_URL

    @property
    def namespace(self) -> str:
        """
        The authorized user's account login, e.g. ``alice``.

        Fetched from the API profile (``GET /user``) on first use and
        cached; never taken from user input, so a mistyped owner is
        impossible.
        """
        if self._namespace is None:
            data = self._request("GET", "/user").json()
            self._namespace = data.get("login")
            if not self._namespace:
                raise ValueError(f"user profile lacks a login: {data}")
        return self._namespace

    # ---------- low-level requests ----------

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Send a request authenticated with the Bearer token; raise on non-2xx."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = dict(kwargs.pop("headers", None) or {})
        headers["Authorization"] = f"Bearer {self.access_token}"
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        response = self.session.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response

    def _wait_repo(self, path: str, timeout: float | None = None) -> dict:
        """Poll until the repository ``path`` is visible to the API (forks may be async)."""
        deadline = time.monotonic() + (
            timeout if timeout is not None else self.max_poll * self.poll_interval
        )
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                resp = self._request(
                    "GET", f"/repos/{quote(self.namespace)}/{quote(path)}"
                )
                return resp.json()
            except requests.exceptions.HTTPError as e:
                last = e
                if e.response is None or e.response.status_code != 404:
                    raise
            time.sleep(self.poll_interval)
        raise ConnectionError(
            f"Repository {self.namespace}/{path} did not appear in time"
        ) from last

    def wait_ready(self, timeout: float | None = None) -> dict:
        """Block until this repository is visible to the API; return its info."""
        return self._wait_repo(self.repo, timeout)

    # ---------- fork-source parsing ----------

    @classmethod
    def _split_fork(cls, fork: str) -> tuple[str, str]:
        """
        Parse a GitHub fork source address into (owner, repo).

        Accepts:
            "owner/repo"
            "owner/repo.git"
            "https://github.com/owner/repo"
            "https://github.com/owner/repo.git"
            "github.com/owner/repo"

        Raises:
            ValueError: malformed address, or a non-GitHub source.
                Cross-platform forks are not supported yet — the GitHub API
                cannot import them; import the repository manually on the
                GitHub web UI instead.
        """
        src = fork.strip().rstrip("/")
        host: str | None = None
        if "://" in src:
            _, _, rest = src.partition("://")
            host, _, src = rest.partition("/")
        if "@" in src or (host is not None and host not in cls._FORK_HOSTS):
            raise ValueError(
                "cross-platform forks are not supported yet: the GitHub "
                "API cannot import them; import the repository manually on "
                f"the GitHub web UI instead (got {fork!r})"
            )
        parts = [p for p in src.split("/") if p]
        if len(parts) < 2:
            raise ValueError(
                f"fork must look like 'owner/repo' or a full GitHub URL, got {fork!r}"
            )
        if parts[0] in cls._FORK_HOSTS:
            parts = parts[1:]
            if len(parts) < 2:
                raise ValueError(
                    f"fork must look like 'owner/repo' or a full GitHub URL, got {fork!r}"
                )
        owner, repo = parts[-2], parts[-1]
        return owner, repo.removesuffix(".git")

    # ---------- repository lifecycle ----------

    def ensure_repo_exists(self) -> bool:
        """
        Make sure the target repository exists; return True when it does.

        - repo mode: create ``<login>/repo`` when missing (existing -> no-op);
        - fork mode: reuse an existing same-named repository, otherwise fork
          the GitHub source under the same name.
        """
        if self._repo_exists():
            return True
        if self.fork is not None:
            self.fork_repo(self.fork)
        else:
            self.create_repo()
        return True

    def _repo_exists(self) -> bool:
        """True if ``<login>/repo`` is visible to the API."""
        try:
            self._request("GET", f"/repos/{quote(self.namespace)}/{quote(self.repo)}")
            return True
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return False
            raise

    def create_repo(
        self, description: str | None = None, auto_init: bool = True
    ) -> dict:
        """
        Create a new repository and wait until it is visible to the API.

        With ``auto_init=True`` the repository is initialized with a README
        (first commit + default branch), which the contents API needs
        before the first file write.
        """
        data = {
            "name": self.repo,
            "description": description or f"{self.namespace}/{self.repo}",
            "has_issues": False,
            "has_wiki": False,
            "auto_init": auto_init,
        }
        resp = self._request("POST", "/user/repos", json=data)
        created = resp.json()
        self._wait_repo(created.get("name") or self.repo)
        return created

    def fork_repo(self, fork: str, organization: str | None = None) -> dict:
        """
        Fork a *GitHub* repository into this account under its original name.

        The fork API does not support custom names, so the fork always keeps
        the source's name (the constructor already resolved the target to
        ``<login>/<source name>``). If the API reports a different path it
        is renamed defensively.
        """
        src_owner, src_repo = self._split_fork(fork)
        data: dict[str, Any] = {}
        if organization:
            data["organization"] = organization
        resp = self._request(
            "POST", f"/repos/{quote(src_owner)}/{quote(src_repo)}/forks", json=data
        )
        created = resp.json()
        path = (
            created.get("path")
            or created.get("name")
            or created.get("full_name", "").rsplit("/", 1)[-1]
        )
        if not path:
            raise ValueError(f"fork response lacks a repository path: {created}")
        self._wait_repo(path)
        if path != self.repo:
            # Set the display name to self.repo (no path rename on GitHub).
            self._request(
                "PATCH",
                f"/repos/{quote(self.namespace)}/{quote(path)}",
                json={"name": self.repo},
            )
        return created

    def delete_repo(self) -> None:
        """Delete this repository (tests/cleanup only)."""
        self._request("DELETE", f"/repos/{quote(self.namespace)}/{quote(self.repo)}")

    # ---------- file operations (the Storage contract) ----------

    def push(
        self, file_path: str, content_bytes: bytes, commit_message: str | None = None
    ) -> dict:
        """
        Create or update a file in the repository; return GitHub's JSON response.

        The shared flow: look up the current blob sha, build the contents
        payload, then write through ``_write_file`` — retrying briefly the
        transient fork-materialization race (``_is_fork_race``).
        """
        endpoint = (
            f"/repos/{quote(self.namespace)}/{quote(self.repo)}"
            f"/contents/{quote(file_path, safe='/')}"
        )
        content_b64 = base64.b64encode(content_bytes).decode("ascii")

        sha = self._existing_sha(endpoint)
        if commit_message is None:
            commit_message = (
                f"Update file {file_path}" if sha else f"Create file {file_path}"
            )

        payload: dict[str, Any] = {
            "message": commit_message,
            "content": content_b64,
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        response: requests.Response | None = None
        for attempt in range(self._WRITE_RETRIES):
            try:
                response = self._write_file(endpoint, payload, sha)
                break
            except requests.exceptions.HTTPError as e:
                # Retry the transient fork-materialization race (see the
                # module docstring); anything else propagates immediately.
                if attempt + 1 < self._WRITE_RETRIES and self._is_fork_race(e):
                    time.sleep(self._WRITE_BACKOFF * (attempt + 1))
                    continue
                raise
        assert response is not None
        return response.json()

    def _write_file(
        self, endpoint: str, payload: dict, sha: str | None
    ) -> requests.Response:
        """GitHub uses a single PUT endpoint for both create and update."""
        return self._request("PUT", endpoint, json=payload)

    def _is_fork_race(self, exc: requests.exceptions.HTTPError) -> bool:
        """True if the error is GitHub's transient fork-materialization race.

        The fork record appears to the API quickly, but the default branch
        is still being initialized, so a write issued right after forking
        can transiently fail with 409 "Git Repository is empty" / 422.
        """
        if exc.response is None or exc.response.status_code not in (409, 422):
            return False
        text = (exc.response.text or "").lower()
        return "empty" in text or "repository" in text

    def _existing_sha(self, endpoint: str) -> str | None:
        """Return the file's current sha, or None if the file does not exist.

        A missing file is reported either as HTTP 404 or as an empty list;
        a non-empty list means the path is a directory.
        """
        try:
            resp = self._request("GET", endpoint, params={"ref": self.branch})
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise
        data = resp.json()
        if isinstance(data, list):
            if data:
                raise ValueError(
                    f"Path is a directory: {endpoint.rsplit('/', 1)[-1]}"
                )
            return None
        return data.get("sha")

    # ---------- subscriber-facing links ----------

    def raw_url(self, path: str) -> str:
        """The raw.githubusercontent.com URL of ``path`` in this repository."""
        return (
            f"https://raw.githubusercontent.com/{self.namespace}/{self.repo}"
            f"/{self.branch}/{quote(path, safe='/')}"
        )

    def spore_link(self, path: str, vk: bytes) -> str:
        """
        Build a subscriber spore link for ``path`` (cdn-accelerated when enabled).

        The raw URL is passed through ``self.cdn`` (``None`` when the
        ``cdn`` constructor argument was ``False``) before being split into
        host/path for the spore. For a private repository keep the default
        ``cdn=False`` — the subscriber then needs an authenticated session
        for the raw host.
        """
        url = self.raw_url(path)
        if self.cdn is not None:
            url = self.cdn(url)
        rest = url.removeprefix("https://")
        host, _, spore_path = rest.partition("/")
        return Spore(host, spore_path, vk).export()


if __name__ == "__main__":
    # Usage demo: the token is always passed explicitly.
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: python -m mycelium.interface.sower.github <access_token>"
        )
    token = sys.argv[1]

    # Repo mode: manage <login>/repo (create it when missing), then push.
    # The account login is resolved automatically from the authorized user's
    # profile — there is no owner parameter. Demos hardcode cdn=True so the
    # spore link is accelerated via jsDelivr.
    client = GithubClient(
        access_token=token,
        repo="my-feed-repo",
        branch="main",
        cdn=True,
    )
    client.ensure_repo_exists()

    # Publish/update the feed file.
    feed_data: bytes = b"your_exported_feed_bytes"
    result = client.push(
        "feed.dat", feed_data, commit_message="Publish feed update"
    )
    print("File pushed. SHA:", result.get("content", {}).get("sha"))

    # Subscriber link, accelerated via jsDelivr (cdn=True above).
    vk_hex = "abcd" * 8  # replace with your real verification key
    print("Spore link:", client.spore_link("feed.dat", bytes.fromhex(vk_hex)))

    # Fork mode (disguise): fork a *GitHub* source into a same-named repo.
    # Exactly one of repo/fork may be given; reuse is automatic when the
    # same-named repository already exists in the account.
    # client = GithubClient(
    #     access_token=token,
    #     fork="some_owner/some_repo",
    # )
    # client.ensure_repo_exists()
