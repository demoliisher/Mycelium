# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Pure-Python single-file git push backend (dulwich), no system git required.

Platform modules that write the feed blob with a real ``git push`` (CNB has
no contents write API) share this backend instead of shelling out to the
``git`` executable — there is nothing to install or configure on the user's
machine, the commit identity is written directly into the commit object
(the platform API resolves it, not the local ``git config``), and the whole
operation runs in memory: no clone, no working tree, no temporary
credential store.

``GitPusher`` is transport-agnostic in the dulwich sense: the ``url`` is
passed through ``dulwich.client.get_transport_and_path``, so it accepts an
HTTPS URL (the CNB case) as well as a local path or ``file://`` URL — the
latter lets the unit tests exercise a real push against a local bare
repository without any network.

The push protocol is the standard git smart HTTP: the current remote tip of
the target branch is read first (``refs/heads/<branch>``, or nothing for an
unborn branch), then a single commit is built in memory — a blob with the
file bytes, a tree with the path (nested paths become nested trees), a
commit carrying the platform-provided author/committer identity and the
remote tip as its parent — and the objects are uploaded with
``client.send_pack``. A fresh repository therefore gets a proper root
commit on the first push instead of racing the server-side branch
initialization.
"""

from __future__ import annotations

import time

from dulwich.client import HTTPProxyUnauthorized, HTTPUnauthorized, get_transport_and_path
from dulwich.errors import GitProtocolError, HangupException, NotGitRepository
from dulwich.objects import Blob, Commit, Tree
from dulwich.pack import pack_objects_to_data

__all__ = [
    "GIT_ERRORS",
    "GIT_PUSH_TIMEOUT",
    "GitPusher",
    "is_transient_git_error",
]

# A push can take a while on slow links; bound every network call.
GIT_PUSH_TIMEOUT = 300.0

# The dulwich errors a push can raise. ``SendPackError`` subclasses
# ``GitProtocolError``; platform ``push`` methods catch this tuple around
# their git write so no dulwich-internal exception escapes as-is.
GIT_ERRORS = (GitProtocolError, NotGitRepository, HTTPUnauthorized, HTTPProxyUnauthorized)


def is_transient_git_error(exc: Exception) -> bool:
    """
    True if a dulwich push failure looks transient and worth retrying.

    Mirrors the old ``git``-subprocess heuristic: a fresh repository whose
    server-side branch is still being initialized answers with a 404
    (``NotGitRepository``), a 5xx or a dropped connection
    (``HangupException`` / network errors wrapped in ``GitProtocolError``).
    Authentication failures (401/407) and rejected packs are not transient.
    """
    from dulwich.errors import SendPackError

    if isinstance(exc, (HTTPUnauthorized, HTTPProxyUnauthorized, SendPackError)):
        return False
    if isinstance(exc, NotGitRepository):
        return True  # fresh repo: the git endpoint is not ready yet
    if isinstance(exc, HangupException):
        return True  # connection dropped mid-push
    if isinstance(exc, GitProtocolError):
        text = str(exc).lower()
        if "unexpected http resp" in text:
            return "unexpected http resp 5" in text  # 5xx transient, 4xx not
        return any(
            marker in text
            for marker in (
                "connection",
                "timeout",
                "timed out",
                "reset",
                "unreachable",
                "eof",
            )
        )
    return False


class GitPusher:
    """
    Minimal pure-Python single-file git push (dulwich backend).

    ``push_file`` writes one file into the remote repository as a single
    commit and fast-forwards ``refs/heads/<branch>`` to it. Everything is
    built in memory and uploaded over the git smart HTTP protocol — no
    ``git`` executable, no clone, no working tree, no credential store.

    The constructor takes the remote ``url`` (e.g.
    ``https://cnb.cool/mycelium/my-feed``) and the git credentials
    (``username`` + ``password`` — the CNB remote accepts ``cnb`` with the
    access token as the password); a local path or ``file://`` URL is
    accepted too (used by the tests).
    """

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        timeout: float = GIT_PUSH_TIMEOUT,
    ):
        self.url = url
        self.username = username
        self.password = password
        self.timeout = timeout

    def head(self, branch: str) -> str | None:
        """
        The remote tip of ``branch`` (hex sha), or None when the branch is
        unborn (a fresh repository has no refs at all).
        """
        client, path = self._transport()
        refs = client.get_refs(path.encode()).refs
        sha = refs.get(f"refs/heads/{branch}".encode())
        return sha.decode("ascii") if sha else None

    def push_file(
        self,
        branch: str,
        path: str,
        content: bytes,
        message: str,
        author_name: str,
        author_email: str,
    ) -> dict:
        """
        Create or overwrite ``path`` with ``content`` in a single commit
        and push it to ``refs/heads/<branch>``.

        The commit's author and committer are ``author_name`` /
        ``author_email`` verbatim — the caller resolves them from the
        platform API, so no local ``git config`` is involved. The commit
        parents are the remote tip of ``branch`` (a fresh repository gets a
        root commit).

        Returns:
            A summary dict: ``{"commit": {"sha": <hex sha>}, "message": <message>}``
        """
        tip = self.head(branch)
        parent = bytes.fromhex(tip) if tip else None
        objects, commit = self._build_objects(
            path, content, message, author_name, author_email, parent
        )
        client, repo_path = self._transport()
        client.send_pack(
            repo_path.encode(),
            lambda old: {f"refs/heads/{branch}".encode(): commit.id},
            lambda have, want, **kw: pack_objects_to_data(objects),
        )
        return {
            "commit": {"sha": commit.id.decode("ascii")},
            "message": message,
        }

    # ---------- internals ----------

    def _transport(self):
        """The (client, repo path) pair for ``self.url`` (dulwich resolves the transport)."""
        return get_transport_and_path(
            self.url,
            username=self.username,
            password=self.password,
            operation="push",
        )

    def _build_objects(
        self,
        path: str,
        content: bytes,
        message: str,
        author_name: str,
        author_email: str,
        parent: bytes | None,
    ):
        """Build the blob/tree/commit objects for one file; return (objects, commit).

        ``objects`` is a list of ``(ShaFile, None)`` pairs ready for
        ``pack_objects_to_data``. The tree nests ``path`` segments, so a
        path like ``dir/sub/feed.dat`` becomes a tree of trees.
        """
        clean = path.strip("/")
        if not clean:
            raise ValueError("cannot push an empty file path")
        blob = Blob.from_string(content)
        root, trees = _build_tree(clean, blob)
        commit = Commit()
        commit.tree = root.id
        commit.author = commit.committer = (
            f"{author_name} <{author_email}>".encode("utf-8")
        )
        commit.message = message.encode("utf-8")
        commit.parents = [parent] if parent is not None else []
        now = int(time.time())
        tz = time.localtime().tm_gmtoff
        commit.author_time = commit.commit_time = now
        commit.author_timezone = commit.commit_timezone = tz
        objects = [(blob, None)] + [(t, None) for t in trees]
        objects.append((commit, None))
        return objects, commit


def _build_tree(path: str, blob: Blob) -> tuple[Tree, list[Tree]]:
    """Build the tree(s) for ``path``; return (root tree, all trees).

    A flat path produces a single tree holding the blob; a nested path
    produces a chain of directory trees (mode 0o40000) ending in the file
    tree (mode 0o100644).
    """
    parts = path.split("/")
    root = Tree()
    trees: list[Tree] = []
    if len(parts) == 1:
        root.add(parts[0].encode("utf-8"), 0o100644, blob.id)
        trees.append(root)
        return root, trees
    current = Tree()
    current.add(parts[-1].encode("utf-8"), 0o100644, blob.id)
    trees.append(current)
    for segment in reversed(parts[1:-1]):
        parent_tree = Tree()
        parent_tree.add(segment.encode("utf-8"), 0o40000, current.id)
        trees.append(parent_tree)
        current = parent_tree
    root.add(parts[0].encode("utf-8"), 0o40000, current.id)
    trees.append(root)
    return root, trees
