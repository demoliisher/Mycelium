# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
CNB platform module (sower side): push the encrypted feed into a cnb.cool repository.

CNB (cnb.cool) is Tencent Cloud's cloud-native code-hosting platform. Its
OpenAPI differs from Gitee/GitCode/GitHub in three ways that shape this
module:

- **Repositories live inside organizations** (组织). CNB has no personal
  repository concept, so the constructor takes the organization path
  explicitly (``group``) and creates it when missing (needs the
  ``group-manage`` token scope). The ``namespace`` therefore is the
  organization path, not the profile login — the one deviation from the
  shared ``GitPlatformClient`` contract, which resolves the namespace from
  ``GET /user`` everywhere else.
- **There is no contents write API.** ``push`` writes the blob with a real
  ``git push``: the module clones the repository into a temporary directory,
  overwrites the file, commits and pushes (username ``cnb``, the access
  token as the password — this is what the ``repo-code`` scope's "Git
  client credentials" grants). The ``_write_file`` contract hook therefore
  has no HTTP counterpart on CNB and raises.
- **There is no fork API.** The ``fork`` constructor argument is accepted
  (the target name is parsed like on the other platforms) but any attempt
  to use it raises with a hint to fork the repository manually on the CNB
  web UI.

Two further platform quirks:

- The API authenticates with an ``Authorization: Bearer`` header (like
  GitHub), and the raw content endpoint requires the token even for public
  repositories — CNB spore links always need an authenticated picker
  session (``mycelium.interface.picker.Hypha`` with a ``requests.Session``
  that attaches the token).
- The OpenAPI refuses to delete repositories/organizations inside root
  organizations (HTTP 412, "root group management rules") unless the
  platform allows it; ``delete_repo`` propagates that refusal, so cleanup
  may have to happen on the CNB web UI.

The feed blob is written through ``push`` via a git push. Pulling it back
is picker behavior — use ``mycelium.interface.picker`` (``Hypha``) for that.

To avoid polluting the open-source community, **never send pull requests
to upstream repositories** — a forked copy is a disguise container, not a
contribution.

The access token is **not** embedded in this module; it is always passed
explicitly as the ``access_token`` constructor argument (or ``sys.argv[1]``
in the ``__main__`` demo). It acts as the git password during ``push`` and
is handed to git through a temporary credential store that is deleted right
after the push — it never appears in a URL or on the command line.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

import requests

from mycelium.protocol import Spore

from .base import GitPlatformClient

__all__ = ["CnbClient"]

# The CNB git remote authenticates with the fixed username ``cnb`` and the
# access token as the password (see docs.cnb.cool/guide/access-token).
_GIT_USERNAME = "cnb"

# Neutral commit identity used on the feed repository unless ``git_author``
# is given; sowers should pick an identity that cannot be linked back to
# their other platform personas (see AGENTS.md).
_DEFAULT_GIT_AUTHOR = "Mycelium Sower <sower@mycelium.local>"

# A push can take a while on slow links; bound every git subprocess call.
_GIT_TIMEOUT = 300.0


class CnbClient(GitPlatformClient):
    """
    CNB OpenAPI client bound to a single repository (sower side).

    Exactly one of ``repo`` / ``fork`` must be given (mutually exclusive):

    - ``repo`` mode: the target is ``<group>/repo`` — the repository is
      created when missing and the organization ``group`` is created too when
      it does not exist yet (CNB repositories live inside organizations);
    - ``fork`` mode: accepted for API compatibility but **always raises**
      when used — CNB has no fork-creation endpoint; fork the repository
      manually on the CNB web UI and then use ``repo`` mode.

    ``namespace`` is the organization path ``group`` (CNB has no personal
    repositories); the profile call (``GET /user``) still runs on first use
    to validate the token early.

    ``visibility`` selects the repository visibility on creation
    (``public`` / ``private`` / ``secret``; CNB defaults to ``public``).
    ``git_author`` is the commit identity written into the feed repository's
    git history, as ``"Name <email>"``.
    """

    BASE_URL = "https://api.cnb.cool"
    default_branch = "main"
    _FORK_HOSTS = ("cnb.cool",)

    def __init__(
        self,
        access_token: str,
        repo: str | None = None,
        fork: str | None = None,
        group: str | None = None,
        branch: str | None = None,
        visibility: str = "public",
        git_author: str | None = None,
        poll_interval: float = 1.0,
        max_poll: int = 30,
    ):
        if (repo is None) == (fork is None):
            raise ValueError(
                "exactly one of repo/fork must be given "
                "(they are mutually exclusive)"
            )
        if visibility not in ("public", "private", "secret"):
            raise ValueError(
                f"visibility must be 'public', 'private' or 'secret', got {visibility!r}"
            )
        self.access_token = access_token
        self.fork = fork
        if fork is not None:
            # Fork mode: the target keeps the source's name (the CNB fork API
            # does not exist — using fork mode raises at call time).
            self.repo = self._split_fork(fork)[1]
            self.group = group or ""  # unused: fork_repo always raises
        else:
            assert repo is not None
            self.repo = repo
            if not group:
                raise ValueError(
                    "CNB repositories live inside organizations: pass the "
                    "organization path (group=...); it is created when missing"
                )
            self.group = group
        self.visibility = visibility
        self.git_author = git_author or _DEFAULT_GIT_AUTHOR
        match = re.match(r"^(?P<name>.+?)\s*<(?P<email>[^<>]+)>$", self.git_author)
        if not match:
            raise ValueError(
                f"git_author must look like 'Name <email>', got {self.git_author!r}"
            )
        self._git_name = match.group("name").strip()
        self._git_email = match.group("email").strip()
        self.branch = branch or self.default_branch
        self.poll_interval = poll_interval
        self.max_poll = max_poll
        self.session = requests.Session()
        self._namespace: str | None = None  # lazy cache of the namespace

    @property
    def base_url(self) -> str:
        """The API root of this platform."""
        return self.BASE_URL

    @property
    def namespace(self) -> str:
        """
        The target organization path, e.g. ``mycelium`` — CNB's namespace.

        CNB has no personal repositories: the namespace is the organization
        path given by the caller (``group``), not the profile login. The
        first access still fetches the profile (``GET /user``) to validate
        the token early.
        """
        if self._namespace is None:
            self._request("GET", "/user")
            self._namespace = self.group
        return self._namespace

    # ---------- low-level requests ----------

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Send a request authenticated with the Bearer token; raise on non-2xx."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = dict(kwargs.pop("headers", None) or {})
        headers["Authorization"] = f"Bearer {self.access_token}"
        headers["Accept"] = "application/json"
        response = self.session.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response

    def _group_path(self) -> str:
        """The URL path of the organization (each segment quoted, slashes kept)."""
        return "/".join(quote(seg, safe="") for seg in self.group.split("/"))

    def _repo_path(self) -> str:
        """The URL path of the target repository (``group/repo``)."""
        return f"{self._group_path()}/{quote(self.repo, safe='')}"

    def _contents_endpoint(self, file_path: str) -> str:
        """The contents endpoint of ``file_path`` in the target repository."""
        return f"/{self._repo_path()}/-/git/contents/{quote(file_path, safe='/')}"

    def _wait_repo(self, path: str, timeout: float | None = None) -> dict:
        """Poll until the repository ``path`` is visible to the API (creation may be async)."""
        deadline = time.monotonic() + (
            timeout if timeout is not None else self.max_poll * self.poll_interval
        )
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                resp = self._request("GET", f"/{self._repo_path()}")
                return resp.json()
            except requests.exceptions.HTTPError as e:
                last = e
                if e.response is None or e.response.status_code != 404:
                    raise
            time.sleep(self.poll_interval)
        raise ConnectionError(
            f"Repository {self.group}/{path} did not appear in time"
        ) from last

    def wait_ready(self, timeout: float | None = None) -> dict:
        """Block until this repository is visible to the API; return its info."""
        return self._wait_repo(self.repo, timeout)

    # ---------- fork-source parsing ----------

    @classmethod
    def _split_fork(cls, fork: str) -> tuple[str, str]:
        """
        Parse a CNB fork source address into (owner, repo).

        Accepts:
            "owner/repo"
            "owner/repo.git"
            "https://cnb.cool/owner/repo"
            "https://cnb.cool/owner/repo.git"
            "cnb.cool/owner/repo"

        ``owner`` may itself be a nested organization path ("org/sub/repo").

        Raises:
            ValueError: malformed address, or a non-CNB source.
                Cross-platform forks are not supported yet — and CNB has no
                fork-creation endpoint at all; fork the repository manually
                on the CNB web UI and use repo mode instead.
        """
        src = fork.strip().rstrip("/")
        host: str | None = None
        if "://" in src:
            _, _, rest = src.partition("://")
            host, _, src = rest.partition("/")
        if "@" in src or (host is not None and host not in cls._FORK_HOSTS):
            raise ValueError(
                "cross-platform forks are not supported yet: the CNB API "
                "cannot import them; fork the repository manually on the "
                f"CNB web UI and use repo mode instead (got {fork!r})"
            )
        parts = [p for p in src.split("/") if p]
        if len(parts) < 2:
            raise ValueError(
                f"fork must look like 'owner/repo' or a full CNB URL, got {fork!r}"
            )
        if parts[0] in cls._FORK_HOSTS:
            parts = parts[1:]
            if len(parts) < 2:
                raise ValueError(
                    f"fork must look like 'owner/repo' or a full CNB URL, got {fork!r}"
                )
        repo = parts[-1].removesuffix(".git")
        owner = "/".join(parts[:-1])
        return owner, repo

    # ---------- repository lifecycle ----------

    def ensure_repo_exists(self) -> bool:
        """
        Make sure the target repository exists; return True when it does.

        - repo mode: create ``<group>/repo`` when missing (existing -> no-op);
        - fork mode: **raises** — CNB has no fork-creation endpoint; fork
          the repository manually on the CNB web UI and use repo mode.
        """
        if self._repo_exists():
            return True
        if self.fork is not None:
            self.fork_repo(self.fork)
        else:
            self.create_repo()
        return True

    def _repo_exists(self) -> bool:
        """True if ``<group>/repo`` is visible to the API."""
        try:
            self._request("GET", f"/{self._repo_path()}")
            return True
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return False
            raise

    def _ensure_group(self) -> None:
        """Create the organization when missing (CNB repositories live in orgs)."""
        try:
            self._request("GET", f"/{self._group_path()}")
        except requests.exceptions.HTTPError as e:
            if e.response is None or e.response.status_code != 404:
                raise
            if "/" in self.group:
                raise ValueError(
                    "cannot auto-create a nested organization path: CNB only "
                    f"creates root organizations, got {self.group!r}; create "
                    "the parent organization on the CNB web UI first"
                )
            self._request(
                "POST",
                "/groups",
                json={"path": self.group, "remark": "", "description": ""},
            )

    def create_repo(
        self, description: str | None = None, auto_init: bool = True
    ) -> dict:
        """
        Create a new repository (and its organization when missing) and wait
        until it is visible to the API.

        CNB has no repository-initialization flag: the repository is created
        empty and the first ``push`` (a git push) initializes the default
        branch. ``auto_init`` is accepted for contract compatibility and
        ignored.
        """
        self._ensure_group()
        data = {
            "name": self.repo,
            "description": description or f"{self.group}/{self.repo}",
            "visibility": self.visibility,
        }
        resp = self._request("POST", f"/{self._group_path()}/-/repos", json=data)
        try:
            created = resp.json()
        except ValueError:
            created = {}
        self._wait_repo(self.repo)
        return created

    def fork_repo(self, fork: str, organization: str | None = None) -> dict:
        """
        CNB has no fork API — always raises with a manual-fork hint.

        The ``fork`` constructor argument is accepted (the target name is
        parsed like on the other platforms), but any attempt to use it
        raises: fork the repository manually on the CNB web UI and then use
        repo mode with the organization that now contains the fork.
        """
        raise ValueError(
            "the CNB API has no fork endpoint: fork the repository manually "
            "on the CNB web UI, then use repo mode with the organization "
            f"that now contains the fork (got {fork!r})"
        )

    def delete_repo(self) -> None:
        """Delete this repository (tests/cleanup only).

        CNB may refuse with HTTP 412 ("root group management rules") for
        repositories inside protected root organizations — the platform then
        requires deletion through the CNB web UI. A refused first attempt
        may also carry an ``x-cnb-identity-ticket`` that must be echoed back
        (the swagger documents the header); that retry is handled here.
        """
        endpoint = f"/{self._repo_path()}"
        headers: dict[str, str] = {}
        for attempt in range(2):
            try:
                self._request("DELETE", endpoint, headers=headers)
                return
            except requests.exceptions.HTTPError as e:
                ticket = _identity_ticket(e.response)
                if attempt == 0 and ticket is not None:
                    headers["X-Cnb-Identity-Ticket"] = ticket
                    continue
                raise

    # ---------- file operations (the Storage contract) ----------

    def push(
        self, file_path: str, content_bytes: bytes, commit_message: str | None = None
    ) -> dict:
        """
        Create or update a file with a real git push; return a summary dict.

        CNB has no contents write API: the blob is committed in a temporary
        clone of the repository and pushed to the configured branch (the
        access token acts as the git password, username ``cnb``). Pushing to
        a just-created repository can transiently fail while the branch is
        still being initialized; such errors are retried briefly.
        """
        endpoint = self._contents_endpoint(file_path)
        sha = self._existing_sha(endpoint)
        if commit_message is None:
            commit_message = (
                f"Update file {file_path}" if sha else f"Create file {file_path}"
            )
        for attempt in range(self._WRITE_RETRIES):
            try:
                return self._push_once(file_path, content_bytes, commit_message)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
                if attempt + 1 < self._WRITE_RETRIES and self._is_transient(e):
                    time.sleep(self._WRITE_BACKOFF * (attempt + 1))
                    continue
                raise
        raise AssertionError("unreachable")

    def _push_once(
        self, file_path: str, content_bytes: bytes, commit_message: str
    ) -> dict:
        """Clone the target, overwrite ``file_path``, commit and push."""
        remote = f"https://cnb.cool/{self.group}/{self.repo}"
        cred = self._write_credential_file()
        try:
            with tempfile.TemporaryDirectory(prefix="mycelium-cnb-") as workdir:
                self._git(cred, "clone", remote, workdir)
                # A fresh clone sits on the remote default branch (unborn for
                # an empty repository); move onto the target branch.
                current = self._git(
                    cred, "branch", "--show-current", cwd=workdir
                ).stdout.strip()
                if current != self.branch:
                    try:
                        self._git(cred, "checkout", self.branch, cwd=workdir)
                    except subprocess.CalledProcessError:
                        self._git(cred, "checkout", "-b", self.branch, cwd=workdir)
                self._git(cred, "config", "user.name", self._git_name, cwd=workdir)
                self._git(cred, "config", "user.email", self._git_email, cwd=workdir)
                target = os.path.join(workdir, file_path)
                parent = os.path.dirname(target)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(target, "wb") as f:
                    f.write(content_bytes)
                self._git(cred, "add", "-A", cwd=workdir)
                self._git(cred, "commit", "-m", commit_message, cwd=workdir)
                self._git(cred, "push", remote, f"HEAD:{self.branch}", cwd=workdir)
                head = self._git(cred, "rev-parse", "HEAD", cwd=workdir).stdout.strip()
        finally:
            os.unlink(cred)
        return {"commit": {"sha": head}, "message": commit_message}

    def _write_credential_file(self) -> str:
        """Write a temporary git credential store for the CNB remote."""
        fd, path = tempfile.mkstemp(prefix="mycelium-cnb-cred-", text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"https://{_GIT_USERNAME}:{self.access_token}@cnb.cool\n")
        return path

    def _git(
        self, cred: str, *args: str, cwd: str | None = None
    ) -> subprocess.CompletedProcess:
        """Run ``git`` with the CNB credential store; raise on failure.

        The store file path is passed with forward slashes (git mangles
        backslashes in helper arguments), Git Credential Manager is forced
        non-interactive and terminal prompts are disabled, so the token
        comes only from the temporary store.
        """
        helper = f"store --file={cred.replace(os.sep, '/')}"
        env = os.environ.copy()
        env["GCM_INTERACTIVE"] = "never"
        env["GIT_TERMINAL_PROMPT"] = "0"
        return subprocess.run(
            ["git", "-c", f"credential.helper={helper}", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=_GIT_TIMEOUT,
        )

    def _write_file(
        self, endpoint: str, payload: dict, sha: str | None
    ) -> requests.Response:
        """CNB has no contents write API — raises; ``push`` writes via git."""
        raise NotImplementedError(
            "the CNB API has no contents write endpoint; CnbClient.push "
            "writes files with a real git push instead"
        )

    def _is_fork_race(self, exc: requests.exceptions.HTTPError) -> bool:
        """False: CNB has no fork API, and ``push`` retries git failures itself."""
        return False

    def _is_transient(self, exc: Exception) -> bool:
        """True if a git failure looks like the transient fresh-repo race."""
        if isinstance(exc, subprocess.TimeoutExpired):
            return True
        if isinstance(exc, subprocess.CalledProcessError):
            stderr = (exc.stderr or "").lower()
            return any(
                marker in stderr
                for marker in (
                    "not found",
                    "empty",
                    "initializ",
                    "cannot lock",
                    "could not read from remote",
                )
            )
        return False

    def _existing_sha(self, endpoint: str) -> str | None:
        """Return the file's current sha, or None if the file does not exist.

        A missing file is reported as HTTP 404; an empty repository answers
        the contents endpoint with ``type: "empty"`` (also treated as
        missing), and ``type: "tree"`` means the path is a directory.
        """
        try:
            resp = self._request("GET", endpoint, params={"ref": self.branch})
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise
        data = resp.json()
        kind = data.get("type")
        if kind == "tree":
            raise ValueError(
                f"Path is a directory: {endpoint.rsplit('/', 1)[-1]}"
            )
        if kind in ("empty", None):
            return None
        return data.get("sha")

    # ---------- subscriber-facing links ----------

    def raw_url(self, path: str) -> str:
        """The api.cnb.cool raw URL of ``path`` in this repository."""
        return (
            f"https://api.cnb.cool/{self._repo_path()}/-/git/raw/"
            f"{quote(self.branch, safe='')}/{quote(path, safe='/')}"
        )

    def spore_link(self, path: str, vk: bytes) -> str:
        """
        Build a subscriber spore link for ``path``.

        The CNB raw endpoint requires the token even for public
        repositories, so the picker needs a ``requests.Session`` that
        attaches the access token (see the sower README).
        """
        url = self.raw_url(path)
        rest = url.removeprefix("https://")
        host, _, spore_path = rest.partition("/")
        return Spore(host, spore_path, vk).export()


def _identity_ticket(response: requests.Response | None) -> str | None:
    """Extract the ``x-cnb-identity-ticket`` from a refusal, if any."""
    if response is None:
        return None
    value = response.headers.get("X-Cnb-Identity-Ticket")
    if value:
        return value
    try:
        data = response.json()
    except ValueError:
        return None
    for key in ("identity_ticket", "ticket", "x_cnb_identity_ticket"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


if __name__ == "__main__":
    # Usage demo: the token is always passed explicitly.
    if len(sys.argv) < 3:
        raise SystemExit(
            "usage: python -m mycelium.interface.sower.cnb <access_token> <group>"
        )
    token = sys.argv[1]
    group = sys.argv[2]

    # Repo mode: manage <group>/repo (organization and repository are created
    # when missing), then push. The namespace is the organization path — CNB
    # has no personal repositories, so there is no automatic owner lookup.
    client = CnbClient(
        access_token=token,
        repo="my-feed-repo",
        group=group,
        branch="main",
    )
    client.ensure_repo_exists()

    # Publish/update the feed file.
    feed_data: bytes = b"your_exported_feed_bytes"
    result = client.push(
        "feed.dat", feed_data, commit_message="Publish feed update"
    )
    print("File pushed. SHA:", result.get("commit", {}).get("sha"))

    # Fork mode is not supported by the CNB API: fork the source manually on
    # the CNB web UI, then use repo mode. The constructor accepts fork= only
    # so the target name parses like on the other platforms; using it raises.
    # client = CnbClient(
    #     access_token=token,
    #     fork="some_org/some_repo",
    #     group=group,
    # )
    # client.ensure_repo_exists()
