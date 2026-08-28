"""
Unit tests for the sower interface ``GiteeClient`` (the network layer is
mocked; these tests verify the request paths, parameters and logic branches).
Pulling is picker behavior, so only ``push`` is exercised here.
"""

import base64
import unittest
from unittest import mock

import requests

from mycelium.interface.sower.gitee import GiteeClient

_split_fork = GiteeClient._split_fork  # classmethod under test


class _Resp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data if data is not None else {}
        self.text = ""

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.exceptions.HTTPError(f"{self.status_code} error")
            err.response = self
            raise err


def make_client(**kwargs) -> GiteeClient:
    """Build a client whose ``_request`` is replaced with a recording mock.

    The namespace is pre-seeded so unit tests skip the ``GET /user`` profile
    call; the auto-fetch itself is covered by ``TestNamespace``.
    """
    defaults = dict(access_token="t", repo="my-feed")
    defaults.update(kwargs)
    client = GiteeClient(**defaults)
    client._namespace = "rainbow"
    client._request = mock.Mock()
    return client


def attach(client: GiteeClient, handler):
    """handler(method, endpoint, **kwargs) -> _Resp; emulates _request's raise_for_status."""

    def wrapped(method, endpoint, **kwargs):
        resp = handler(method, endpoint, **kwargs)
        resp.raise_for_status()
        return resp

    client._request.side_effect = wrapped


class TestSplitFork(unittest.TestCase):
    def test_bare_owner_repo(self):
        self.assertEqual(_split_fork("some/src"), ("some", "src"))

    def test_with_git_suffix(self):
        self.assertEqual(_split_fork("some/src.git"), ("some", "src"))

    def test_full_url(self):
        self.assertEqual(
            _split_fork("https://gitee.com/some/src"), ("some", "src")
        )

    def test_full_url_with_git(self):
        self.assertEqual(
            _split_fork("https://gitee.com/some/src.git"), ("some", "src")
        )

    def test_domain_without_scheme(self):
        self.assertEqual(_split_fork("gitee.com/some/src"), ("some", "src"))

    def test_trailing_slash(self):
        self.assertEqual(_split_fork("some/src/"), ("some", "src"))

    def test_bare_name_raises(self):
        with self.assertRaises(ValueError):
            _split_fork("just-a-name")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            _split_fork("")

    def test_cross_platform_url_raises(self):
        with self.assertRaises(ValueError):
            _split_fork("https://github.com/some/src")

    def test_ssh_style_raises(self):
        with self.assertRaises(ValueError):
            _split_fork("git@github.com:some/src.git")


class TestConstructor(unittest.TestCase):
    """repo/fork are mutually exclusive; fork mode targets the source name."""

    def test_repo_mode(self):
        client = GiteeClient("t", repo="my-feed")
        self.assertEqual(client.repo, "my-feed")
        self.assertIsNone(client.fork)

    def test_fork_mode_targets_source_name(self):
        client = GiteeClient("t", fork="some/src")
        self.assertEqual(client.repo, "src")
        self.assertEqual(client.fork, "some/src")

    def test_fork_mode_with_url(self):
        client = GiteeClient("t", fork="https://gitee.com/up/stream.git")
        self.assertEqual(client.repo, "stream")

    def test_neither_repo_nor_fork_raises(self):
        with self.assertRaises(ValueError):
            GiteeClient("t")

    def test_both_repo_and_fork_raise(self):
        with self.assertRaises(ValueError):
            GiteeClient("t", repo="a", fork="b/c")

    def test_malformed_fork_raises(self):
        with self.assertRaises(ValueError):
            GiteeClient("t", fork="no-slash-name")

    def test_cross_platform_fork_raises(self):
        for bad in ("https://github.com/a/b", "git@gitlab.com:a/b.git"):
            with self.assertRaises(ValueError):
                GiteeClient("t", fork=bad)


class TestNamespace(unittest.TestCase):
    """The personal space is fetched from the API profile, not user input."""

    def test_namespace_fetched_from_user_profile(self):
        client = GiteeClient("t", repo="my-feed")
        client._request = mock.Mock(return_value=_Resp(200, {"login": "rainbow"}))
        self.assertEqual(client.namespace, "rainbow")
        client._request.assert_called_once_with("GET", "/user")

    def test_namespace_cached(self):
        client = GiteeClient("t", repo="my-feed")
        client._request = mock.Mock(return_value=_Resp(200, {"login": "rainbow"}))
        _ = client.namespace
        _ = client.namespace
        self.assertEqual(client._request.call_count, 1)

    def test_namespace_missing_login_raises(self):
        client = GiteeClient("t", repo="my-feed")
        client._request = mock.Mock(return_value=_Resp(200, {}))
        with self.assertRaises(ValueError):
            _ = client.namespace


class TestEnsureRepoExists(unittest.TestCase):
    def test_repo_exists_does_nothing(self):
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint))
            return _Resp(200, {"path": "my-feed"})

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())
        self.assertEqual(calls, [("GET", "/repos/rainbow/my-feed")])

    def test_create_when_missing(self):
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/repos/rainbow/my-feed":
                # 1st GET: existence check (404); later GETs: post-create polling (200)
                first = len([c for c in calls if c[0] == "GET" and c[1] == endpoint]) == 1
                return _Resp(404, {}) if first else _Resp(200, {"path": "my-feed"})
            if method == "POST" and endpoint == "/user/repos":
                return _Resp(201, {"path": "my-feed", "name": "my-feed"})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())

        post = next(c for c in calls if c[0] == "POST")
        self.assertEqual(post[1], "/user/repos")
        body = post[2]["json"]
        self.assertEqual(body["name"], "my-feed")
        self.assertFalse(body["has_issues"])
        self.assertFalse(body["has_wiki"])
        self.assertTrue(body["auto_init"])

    def test_fork_when_missing(self):
        """Fork mode: target missing -> fork the source under its own name, no rename."""
        client = make_client(repo=None, fork="some/src")
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/repos/rainbow/src":
                # 1st GET: existence check (404); later GETs: post-fork polling (200)
                first = len([c for c in calls if c[0] == "GET" and c[1] == endpoint]) == 1
                return _Resp(404, {}) if first else _Resp(200, {"path": "src"})
            if method == "POST" and endpoint == "/repos/some/src/forks":
                return _Resp(201, {"path": "src", "name": "src"})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())

        self.assertEqual(client.repo, "src")  # target keeps the source name
        post = next(c for c in calls if c[0] == "POST")
        self.assertEqual(post[1], "/repos/some/src/forks")
        self.assertFalse(any(c[0] == "PATCH" for c in calls))  # same-name: no rename

    def test_fork_reuses_existing(self):
        """Fork mode: same-named repo already exists -> reuse, no fork call."""
        client = make_client(repo=None, fork="some/src")
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/repos/rainbow/src":
                return _Resp(200, {"path": "src"})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())
        self.assertFalse(any(c[0] == "POST" for c in calls))

    def test_fork_with_url_source(self):
        client = make_client(repo=None, fork="https://gitee.com/up/stream.git")
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/repos/rainbow/stream":
                return _Resp(404, {}) if len(calls) == 1 else _Resp(200, {"path": "stream"})
            if method == "POST" and endpoint == "/repos/up/stream/forks":
                return _Resp(201, {"path": "stream", "name": "stream"})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())

        self.assertEqual(client.repo, "stream")
        posts = [c for c in calls if c[0] == "POST"]
        self.assertEqual(posts[0][1], "/repos/up/stream/forks")
        self.assertFalse(any(c[0] == "PATCH" for c in calls))

    def test_other_errors_raise(self):
        client = make_client()

        def handler(method, endpoint, **kwargs):
            return _Resp(500, {})

        attach(client, handler)
        with self.assertRaises(requests.exceptions.HTTPError):
            client.ensure_repo_exists()


class TestPush(unittest.TestCase):
    def test_push_creates_file(self):
        """File missing (GET returns []) -> create via POST, no sha."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, [])  # Gitee returns [] for a missing file
            if method == "POST" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(201, {"content": {"sha": "new-sha"}})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        result = client.push("feed.dat", b"hello")

        post = next(c for c in calls if c[0] == "POST")
        payload = post[2]["json"]
        self.assertNotIn("sha", payload)
        self.assertEqual(payload["message"], "Create file feed.dat")
        self.assertEqual(payload["branch"], "master")
        self.assertEqual(
            payload["content"], base64.b64encode(b"hello").decode("ascii")
        )
        self.assertEqual(result["content"]["sha"], "new-sha")

    def test_push_existing_file(self):
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, {"sha": "old-sha"})
            if method == "PUT" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, {"content": {"sha": "new-sha"}})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        client.push("feed.dat", b"world")

        put = next(c for c in calls if c[0] == "PUT")
        payload = put[2]["json"]
        self.assertEqual(payload["sha"], "old-sha")
        self.assertEqual(payload["message"], "Update file feed.dat")

    def test_push_custom_commit_message(self):
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, {"sha": "s"})
            if method == "PUT" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        client.push("feed.dat", b"x", commit_message="publish v1")
        put = next(c for c in calls if c[0] == "PUT")
        self.assertEqual(put[2]["json"]["message"], "publish v1")

    def test_push_directory_raises(self):
        client = make_client()

        def handler(method, endpoint, **kwargs):
            return _Resp(200, [{"name": "file.txt"}])  # non-empty list -> directory

        attach(client, handler)
        with self.assertRaises(ValueError):
            client.push("dir", b"x")

    def test_push_missing_file_returns_empty_list_creates(self):
        """Gitee returns [] for a missing file; it must be treated as 'create'."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, [])
            if method == "POST" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(201, {"content": {"sha": "s"}})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        client.push("feed.dat", b"x")
        self.assertTrue(any(c[0] == "POST" for c in calls))

    def test_push_retries_fork_race(self):
        """A transient 400 '文件新建失败' right after forking must be retried."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, [])  # missing file -> create
            if method == "POST" and endpoint.endswith("/contents/feed.dat"):
                if len([c for c in calls if c[0] == "POST"]) < 3:
                    resp = _Resp(400, {})
                    resp.text = '{"message":"文件新建失败"}'
                    return resp
                return _Resp(201, {"content": {"sha": "new-sha"}})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        with mock.patch("mycelium.interface.sower.gitee.time.sleep"):
            result = client.push("feed.dat", b"x")

        posts = [c for c in calls if c[0] == "POST"]
        self.assertEqual(len(posts), 3)  # 2 transient failures + 1 success
        self.assertEqual(result["content"]["sha"], "new-sha")

    def test_push_non_race_400_propagates(self):
        """A 400 that is not the fork race must propagate without retry.

        The git-push backup mode is attempted on a non-race failure; when
        the identity is unresolvable (here: profile fetch 403) the original
        API error is re-raised.
        """
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/user":
                return _Resp(403, {})  # backup identity unresolvable
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, [])
            if method == "POST" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(400, {"message": "branch not found"})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        with mock.patch("mycelium.interface.sower.gitee.time.sleep"):
            with self.assertRaises(requests.exceptions.HTTPError):
                client.push("feed.dat", b"x")

        posts = [c for c in calls if c[0] == "POST"]
        self.assertEqual(len(posts), 1)  # no retry on unrelated errors


class TestGitBackup(unittest.TestCase):
    """The git-push backup mode: identity resolution and the fallback path."""

    def test_identity_from_profile(self):
        client = make_client()
        client._request = mock.Mock(
            return_value=_Resp(200, {"login": "rainbow", "email": "me@x"})
        )
        self.assertEqual(client._git_identity(), ("rainbow", "me@x"))

    def test_identity_no_email_returns_none(self):
        client = make_client()
        client._request = mock.Mock(return_value=_Resp(200, {"login": "rainbow"}))
        self.assertIsNone(client._git_identity())

    def test_identity_no_login_returns_none(self):
        client = make_client()
        client._request = mock.Mock(return_value=_Resp(200, {"email": "me@x"}))
        self.assertIsNone(client._git_identity())

    def test_identity_profile_403_returns_none(self):
        client = make_client()
        client._request = mock.Mock(
            side_effect=requests.exceptions.HTTPError("403")
        )
        self.assertIsNone(client._git_identity())

    def test_remote_uses_login_and_token(self):
        client = make_client()
        self.assertEqual(
            client._git_remote(),
            ("https://gitee.com/rainbow/my-feed", "rainbow", "t"),
        )

    def test_push_falls_back_when_api_write_fails(self):
        """A non-race API failure with a resolvable identity -> git-push backup."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/user":
                return _Resp(200, {"login": "rainbow", "email": "me@x"})
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, [])  # missing file (empty list)
            if method == "POST" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(500, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        with mock.patch(
            "mycelium.interface.sower.base.GitPusher"
        ) as pusher_cls, mock.patch(
            "mycelium.interface.sower.gitee.time.sleep"
        ):
            pusher = pusher_cls.return_value
            pusher.push_file.return_value = {"commit": {"sha": "g"}}
            result = client.push("feed.dat", b"x")

        self.assertEqual(result["commit"]["sha"], "g")
        pusher_cls.assert_called_once_with(
            "https://gitee.com/rainbow/my-feed", "rainbow", "t", timeout=300.0
        )
        pusher.push_file.assert_called_once_with(
            "master", "feed.dat", b"x", "Create file feed.dat", "rainbow", "me@x"
        )

    def test_push_no_backup_when_identity_unresolvable(self):
        """No identity (profile 403) -> the original API error propagates."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/user":
                return _Resp(403, {})
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, [])
            if method == "POST" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(500, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        with mock.patch(
            "mycelium.interface.sower.base.GitPusher"
        ) as pusher_cls, mock.patch(
            "mycelium.interface.sower.gitee.time.sleep"
        ):
            with self.assertRaises(requests.exceptions.HTTPError):
                client.push("feed.dat", b"x")
        pusher_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
