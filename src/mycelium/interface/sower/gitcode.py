# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
GitCode platform module (sower side): push the encrypted feed into a GitCode repository.

GitCode and AtomGit are the **same platform** under two names — the API
v5 endpoint is identical on both domains. ``GitCodeClient`` uses
``gitcode.com`` by default and accepts ``atomgit.com`` as an alias
(via the ``host`` argument or in fork source URLs).

The client is bound to exactly one target, chosen by two **mutually
exclusive** constructor arguments:

- ``repo`` — manage ``<namespace>/repo``: create it when missing, then push
  into it (``namespace`` is the personal space, resolved automatically from
  the authorized user's profile — there is no ``owner`` parameter);
- ``fork`` — disguise mode: fork a *GitCode* source repository into this
  account under the **same name** (the fork API does not support custom
  names). If a same-named repository already exists in the account (e.g.
  from an earlier fork), it is reused instead of forking again.

Cross-platform sources (GitHub, Gitee, ...) are **not** supported yet: the
GitCode API cannot import them, so such fork links are rejected with a hint
to import the repository manually on the GitCode web UI.

GitCode materializes forks asynchronously: a write issued right after
forking can transiently collide with the branch initialization
("cannot lock ref"); ``push`` retries such errors briefly.

The feed blob is written through ``push`` via the contents API. Pulling it
back is picker behavior — use ``mycelium.interface.picker``
(``Hypha``) for that.

To avoid polluting the open-source community, **never send pull requests
to upstream repositories** — a forked copy is a disguise container, not a
contribution.

Keep the access token permission-minimal (user-info read + repo read/write
only, if the platform offers scope selection); never commit or share it.
See the sower README for per-platform token guidance.

The access token is **not** embedded in this module; it is always passed
explicitly as the ``access_token`` constructor argument (or ``sys.argv[1]``
in the ``__main__`` demo).
"""

from __future__ import annotations

import base64
import sys
import time
from typing import Any
from urllib.parse import quote

import requests

from .base import GitPlatformClient

__all__ = ["GitCodeClient"]

# The two names of the same platform; ``host`` must be one of these.
_HOSTS = ("gitcode.com", "atomgit.com")

# Note: repository visibility (public/private) is set on the GitCode web
# console; the API creates repositories with the account's default.


class GitCodeClient(GitPlatformClient):
    """
    GitCode API v5 client bound to a single repository (sower side).

    GitCode and AtomGit are the same platform under two names; ``host``
    selects the domain (default ``gitcode.com``, alternative ``atomgit.com``).

    Exactly one of ``repo`` / ``fork`` must be given (mutually exclusive):

    - ``repo`` mode: the target is ``<namespace>/repo`` (created when missing);
    - ``fork`` mode: the target is ``<namespace>/<source name>`` — the fork
      keeps the source's name, since the fork API cannot rename.

    The personal space (``namespace``) is resolved automatically from the
    authorized user's profile (``GET /user``) on first use and cached; there
    is no ``owner`` parameter, so a mistyped owner is impossible.
    """

    _FORK_HOSTS = _HOSTS

    def __init__(
        self,
        access_token: str,
        repo: str | None = None,
        fork: str | None = None,
        host: str = "gitcode.com",
        branch: str | None = None,
        poll_interval: float = 1.0,
        max_poll: int = 30,
    ):
        if host not in _HOSTS:
            raise ValueError(
                f"unsupported GitCode host: {host!r} "
                f"(GitCode and AtomGit are the same platform: {_HOSTS})"
            )
        if (repo is None) == (fork is None):
            raise ValueError(
                "exactly one of repo/fork must be given "
                "(they are mutually exclusive)"
            )
        self.access_token = access_token
        self.host = host
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
        self._namespace: str | None = None  # lazy cache of the personal space

    @property
    def base_url(self) -> str:
        """The API root of the selected domain."""
        return f"https://{self.host}/api/v5"

    @property
    def namespace(self) -> str:
        """
        The authorized user's personal space (个人空间), e.g. ``alice``.

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
        """Send a request with ``access_token`` attached; raise on non-2xx."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        params = dict(kwargs.pop("params", None) or {})
        params["access_token"] = self.access_token
        response = self.session.request(method, url, params=params, **kwargs)
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
        Parse a GitCode fork source address into (owner, repo).

        GitCode and AtomGit are the same platform, so both domains are
        accepted. Accepts:
            "owner/repo"
            "owner/repo.git"
            "https://gitcode.com/owner/repo"
            "https://atomgit.com/owner/repo"
            "gitcode.com/owner/repo"

        Raises:
            ValueError: malformed address, or a non-GitCode source.
                Cross-platform forks are not supported yet — the GitCode
                API cannot import them; import the repository manually on
                the GitCode web UI instead.
        """
        src = fork.strip().rstrip("/")
        host: str | None = None
        if "://" in src:
            _, _, rest = src.partition("://")
            host, _, src = rest.partition("/")
        if "@" in src or (host is not None and host not in cls._FORK_HOSTS):
            raise ValueError(
                "cross-platform forks are not supported yet: the GitCode "
                "API cannot import them; import the repository manually on "
                f"the GitCode web UI instead (got {fork!r})"
            )
        parts = [p for p in src.split("/") if p]
        if len(parts) < 2:
            raise ValueError(
                f"fork must look like 'owner/repo' or a full GitCode URL, got {fork!r}"
            )
        if parts[0] in cls._FORK_HOSTS:
            parts = parts[1:]
            if len(parts) < 2:
                raise ValueError(
                    f"fork must look like 'owner/repo' or a full GitCode URL, got {fork!r}"
                )
        owner, repo = parts[-2], parts[-1]
        return owner, repo.removesuffix(".git")

    # ---------- repository lifecycle ----------

    def ensure_repo_exists(self) -> bool:
        """
        Make sure the target repository exists; return True when it does.

        - repo mode: create ``<namespace>/repo`` when missing (existing -> no-op);
        - fork mode: reuse an existing same-named repository, otherwise fork
          the GitCode source under the same name.
        """
        if self._repo_exists():
            return True
        if self.fork is not None:
            self.fork_repo(self.fork)
        else:
            self.create_repo()
        return True

    def _repo_exists(self) -> bool:
        """True if ``<namespace>/repo`` is visible to the API."""
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
        before the first file write. Visibility (public/private) is set on
        the GitCode web console.
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
        self._wait_repo(created.get("path") or self.repo)
        return created

    def fork_repo(self, fork: str, organization: str | None = None) -> dict:
        """
        Fork a *GitCode* repository into this account under its original name.

        The fork API does not support custom names, so the fork always keeps
        the source's name (the constructor already resolved the target to
        ``<namespace>/<source name>``). If the API reports a different path
        it is renamed defensively.
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
            # Set both the display name and the path to self.repo.
            self._request(
                "PATCH",
                f"/repos/{quote(self.namespace)}/{quote(path)}",
                json={"name": self.repo, "path": self.repo},
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
        Create or update a file in the repository; return the API response.

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
        """
        GitCode splits "create" and "update" into two endpoints:
        - file missing (HTTP 404) → POST /contents/{path} (no sha needed)
        - file exists            → PUT  /contents/{path} (current blob sha required)
        """
        if sha:
            return self._request("PUT", endpoint, json=payload)
        return self._request("POST", endpoint, json=payload)

    def _is_fork_race(self, exc: requests.exceptions.HTTPError) -> bool:
        """True if the error is GitCode's transient fork-materialization race.

        A write issued right after forking can collide with the server-side
        branch initialization ("cannot lock ref ... reference already
        exists"); ``push`` retries such errors briefly.
        """
        if exc.response is None or exc.response.status_code != 400:
            return False
        return "cannot lock ref" in (exc.response.text or "")

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


if __name__ == "__main__":
    # Usage demo: the token is always passed explicitly.
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: python -m mycelium.interface.sower.gitcode <access_token>"
        )
    token = sys.argv[1]

    # Repo mode: manage <namespace>/repo (create it when missing), then push.
    # The namespace (个人空间) is resolved automatically from the authorized
    # user's profile — there is no owner parameter. GitCode and AtomGit are
    # the same platform; `host` selects the domain (gitcode.com default).
    client = GitCodeClient(
        access_token=token,
        repo="my-feed-repo",
        branch="main",
    )
    client.ensure_repo_exists()

    # Publish/update the feed file.
    feed_data: bytes = b"your_exported_feed_bytes"
    result = client.push(
        "feed.dat", feed_data, commit_message="Publish feed update"
    )
    print("File pushed. SHA:", result.get("commit", {}).get("sha"))

    # Fork mode (disguise): fork a *GitCode* source into a same-named repo.
    # Exactly one of repo/fork may be given; reuse is automatic when the
    # same-named repository already exists in the account.
    # client = GitCodeClient(
    #     access_token=token,
    #     fork="some_owner/some_repo",
    # )
    # client.ensure_repo_exists()
