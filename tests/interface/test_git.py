"""
Unit tests for the pure-Python git push backend ``GitPusher``.

The pushes run against a local bare repository (dulwich's ``LocalGitClient``
resolves a filesystem path), so the whole send_pack flow — object building,
pack upload, ref update — is exercised for real without any network or a
``git`` executable.
"""

import tempfile
import unittest

from dulwich.repo import Repo

from mycelium.interface.sower.git import (
    GIT_ERRORS,
    GitPusher,
    is_transient_git_error,
)

from dulwich.errors import GitProtocolError, HangupException, NotGitRepository


class GitPusherTestBase(unittest.TestCase):
    """A local bare repository as the remote, plus a GitPusher bound to it."""

    def setUp(self):
        import os

        self._tmp = tempfile.mkdtemp(prefix="mycelium-git-test-")
        self.remote = f"{self._tmp}/remote"
        os.mkdir(self.remote)  # Repo.init_bare expects the dir to exist
        Repo.init_bare(self.remote)
        self.pusher = GitPusher(self.remote, "cnb", "token")
        self.repo = Repo(self.remote)

    def tearDown(self):
        self.repo.close()
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def read_file(self, path: str) -> bytes:
        """Read ``path`` at the tip of ``main`` from the remote repository."""
        head = self.repo.refs[b"refs/heads/main"]
        commit = self.repo.object_store[head]
        tree = self.repo.object_store[commit.tree]
        entries = {name: (mode, sha) for name, mode, sha in tree.iteritems()}
        for part in path.split("/"):
            mode, sha = entries[part.encode("utf-8")]
            obj = self.repo.object_store[sha]
            if obj.type_name == b"tree":
                tree = obj
                entries = {
                    name: (m, s) for name, m, s in tree.iteritems()
                }
                continue
            return obj.data
        raise AssertionError(f"path not found: {path}")

    def tip_identity(self) -> tuple[str, str, str]:
        """The (author, committer, message) of the tip commit on ``main``."""
        head = self.repo.refs[b"refs/heads/main"]
        commit = self.repo.object_store[head]
        return (
            commit.author.decode("utf-8"),
            commit.committer.decode("utf-8"),
            commit.message.decode("utf-8"),
        )


class TestHead(GitPusherTestBase):
    def test_empty_repo_has_no_head(self):
        self.assertIsNone(self.pusher.head("main"))

    def test_head_after_push(self):
        self.pusher.push_file(
            "main", "feed.dat", b"hello", "Create file feed.dat",
            "Rainbow", "r@e.x",
        )
        head = self.pusher.head("main")
        self.assertEqual(head, self.repo.refs[b"refs/heads/main"].decode("ascii"))

    def test_head_other_branch_missing(self):
        self.pusher.push_file(
            "main", "feed.dat", b"hello", "Create file feed.dat",
            "Rainbow", "r@e.x",
        )
        self.assertIsNone(self.pusher.head("other"))


class TestPushFile(GitPusherTestBase):
    def test_create_file(self):
        result = self.pusher.push_file(
            "main", "feed.dat", b"hello", "Create file feed.dat",
            "Rainbow", "r@e.x",
        )
        self.assertEqual(result["message"], "Create file feed.dat")
        self.assertEqual(
            result["commit"]["sha"],
            self.repo.refs[b"refs/heads/main"].decode("ascii"),
        )
        self.assertEqual(self.read_file("feed.dat"), b"hello")

    def test_update_file_builds_parent_chain(self):
        self.pusher.push_file(
            "main", "feed.dat", b"v1", "one", "Rainbow", "r@e.x",
        )
        first = self.repo.refs[b"refs/heads/main"]
        self.pusher.push_file(
            "main", "feed.dat", b"v2", "two", "Rainbow", "r@e.x",
        )
        head = self.repo.refs[b"refs/heads/main"]
        commit = self.repo.object_store[head]
        self.assertEqual(commit.parents, [bytes.fromhex(first.decode("ascii"))])
        self.assertEqual(self.read_file("feed.dat"), b"v2")

    def test_nested_path(self):
        self.pusher.push_file(
            "main", "dir/sub/feed.dat", b"deep", "nested", "Rainbow", "r@e.x",
        )
        self.assertEqual(self.read_file("dir/sub/feed.dat"), b"deep")

    def test_identity_written_verbatim(self):
        self.pusher.push_file(
            "main", "feed.dat", b"x", "msg", "虹", "rainbow@example.com",
        )
        author, committer, message = self.tip_identity()
        self.assertEqual(author, "虹 <rainbow@example.com>")
        self.assertEqual(committer, "虹 <rainbow@example.com>")
        self.assertEqual(message, "msg")

    def test_empty_path_raises(self):
        with self.assertRaises(ValueError):
            self.pusher.push_file(
                "main", "/", b"x", "msg", "Rainbow", "r@e.x",
            )

    def test_binary_content(self):
        payload = bytes(range(256))
        self.pusher.push_file(
            "main", "feed.dat", payload, "binary", "Rainbow", "r@e.x",
        )
        self.assertEqual(self.read_file("feed.dat"), payload)


class TestTransientDetection(unittest.TestCase):
    def test_not_git_repository_is_transient(self):
        self.assertTrue(is_transient_git_error(NotGitRepository()))

    def test_hangup_is_transient(self):
        self.assertTrue(is_transient_git_error(HangupException()))

    def test_5xx_protocol_error_is_transient(self):
        err = GitProtocolError("unexpected http resp 503 for ...")
        self.assertTrue(is_transient_git_error(err))

    def test_4xx_protocol_error_is_not_transient(self):
        err = GitProtocolError("unexpected http resp 403 for ...")
        self.assertFalse(is_transient_git_error(err))

    def test_network_error_is_transient(self):
        err = GitProtocolError("Connection aborted by remote")
        self.assertTrue(is_transient_git_error(err))

    def test_other_errors_not_transient(self):
        self.assertFalse(is_transient_git_error(ValueError("nope")))
        self.assertFalse(is_transient_git_error(RuntimeError("nope")))

    def test_git_errors_tuple_covers_dulwich_errors(self):
        # The tuple is what platform ``push`` methods catch around git writes.
        for exc in (
            NotGitRepository(),
            HangupException(),
            GitProtocolError("boom"),
        ):
            self.assertIsInstance(exc, GIT_ERRORS)


if __name__ == "__main__":
    unittest.main()
