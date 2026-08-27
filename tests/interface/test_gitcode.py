"""
Unit tests for the sower interface ``GitCodeClient`` (the network layer
is mocked; these tests verify the request paths, parameters and logic
branches). Pulling is picker behavior, so only ``push`` is exercised.
"""

import base64
import unittest
from unittest import mock

import requests

from mycelium.interface.sower.gitcode import GitCodeClient

_split_fork = GitCodeClient._split_fork  # classmethod under test


class _Resp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data if data is not None else {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.exceptions.HTTPError(f"{self.status_code} error")
            err.response = self
            raise err


def make_client(**kwargs) -> GitCodeClient:
    """Build a client whose ``_request`` is replaced with a recording mock.

    The namespace is pre-seeded so unit tests skip the ``GET /user`` profile
    call; the auto-fetch itself is covered by ``TestNamespace``.
    """
    defaults = dict(access_token="t", repo="my-feed")
    defaults.update(kwargs)
    client = GitCodeClient(**defaults)
    client._namespace = "rainbow"
    client._request = mock.Mock()
    return client


def attach(client: GitCodeClient, handler):
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
            _split_fork("https://gitcode.com/some/src"), ("some", "src")
        )

    def test_atomgit_url(self):
        """AtomGit is the same platform under a second name."""
        self.assertEqual(
            _split_fork("https://atomgit.com/some/src.git"), ("some", "src")
        )

    def test_domain_without_scheme(self):
        self.assertEqual(_split_fork("gitcode.com/some/src"), ("some", "src"))

    def test_trailing_slash(self):
        self.assertEqual(_split_fork("some/src/"), ("some", "src"))

    def test_bare_name_raises(self):
        with self.assertRaises(ValueError):
            _split_fork("just-a-name")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            _split_fork("")

    def test_cross_platform_url_raises(self):
        for bad in ("https://github.com/some/src", "https://gitee.com/some/src"):
            with self.assertRaises(ValueError):
                _split_fork(bad)

    def test_ssh_style_raises(self):
        with self.assertRaises(ValueError):
            _split_fork("git@github.com:some/src.git")


class TestConstructor(unittest.TestCase):
    """repo/fork are mutually exclusive; fork mode targets the source name."""

    def test_repo_mode(self):
        client = GitCodeClient("t", repo="my-feed")
        self.assertEqual(client.repo, "my-feed")
        self.assertIsNone(client.fork)
        self.assertEqual(client.host, "gitcode.com")
        self.assertEqual(client.base_url, "https://gitcode.com/api/v5")

    def test_atomgit_host(self):
        client = GitCodeClient("t", repo="my-feed", host="atomgit.com")
        self.assertEqual(client.base_url, "https://atomgit.com/api/v5")

    def test_unsupported_host_raises(self):
        with self.assertRaises(ValueError):
            GitCodeClient("t", repo="my-feed", host="gitlab.com")

    def test_fork_mode_targets_source_name(self):
        client = GitCodeClient("t", fork="some/src")
        self.assertEqual(client.repo, "src")
        self.assertEqual(client.fork, "some/src")

    def test_fork_mode_with_url(self):
        client = GitCodeClient("t", fork="https://atomgit.com/up/stream.git")
        self.assertEqual(client.repo, "stream")

    def test_neither_repo_nor_fork_raises(self):
        with self.assertRaises(ValueError):
            GitCodeClient("t")

    def test_both_repo_and_fork_raise(self):
        with self.assertRaises(ValueError):
            GitCodeClient("t", repo="a", fork="b/c")

    def test_malformed_fork_raises(self):
        with self.assertRaises(ValueError):
            GitCodeClient("t", fork="no-slash-name")

    def test_cross_platform_fork_raises(self):
        for bad in ("https://github.com/a/b", "git@gitlab.com:a/b.git"):
            with self.assertRaises(ValueError):
                GitCodeClient("t", fork=bad)


class TestNamespace(unittest.TestCase):
    """The personal space is fetched from the API profile, not user input."""

    def test_namespace_fetched_from_user_profile(self):
        client = GitCodeClient("t", repo="my-feed")
        client._request = mock.Mock(return_value=_Resp(200, {"login": "rainbow"}))
        self.assertEqual(client.namespace, "rainbow")
        client._request.assert_called_once_with("GET", "/user")

    def test_namespace_cached(self):
        client = GitCodeClient("t", repo="my-feed")
        client._request = mock.Mock(return_value=_Resp(200, {"login": "rainbow"}))
        _ = client.namespace
        _ = client.namespace
        self.assertEqual(client._request.call_count, 1)

    def test_namespace_missing_login_raises(self):
        client = GitCodeClient("t", repo="my-feed")
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
                return _Resp(200, {"path": "my-feed", "name": "my-feed"})
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
                # GitCode's fork response carries full_name instead of path/name.
                return _Resp(200, {"full_name": "rainbow/src", "id": 1})
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

    def test_fork_with_atomgit_url_source(self):
        client = make_client(repo=None, fork="https://atomgit.com/up/stream.git")
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/repos/rainbow/stream":
                return _Resp(404, {}) if len(calls) == 1 else _Resp(200, {"path": "stream"})
            if method == "POST" and endpoint == "/repos/up/stream/forks":
                return _Resp(200, {"full_name": "rainbow/stream"})
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
        """File missing (HTTP 404) -> create via POST, no sha."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})  # GitCode replies 404 for a missing file
            if method == "POST" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, {"commit": {"sha": "new-sha"}})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        result = client.push("feed.dat", b"hello")

        post = next(c for c in calls if c[0] == "POST")
        payload = post[2]["json"]
        self.assertNotIn("sha", payload)
        self.assertEqual(payload["message"], "Create file feed.dat")
        self.assertEqual(payload["branch"], "main")
        self.assertEqual(
            payload["content"], base64.b64encode(b"hello").decode("ascii")
        )
        self.assertEqual(result["commit"]["sha"], "new-sha")

    def test_push_existing_file(self):
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, {"sha": "old-sha"})
            if method == "PUT" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, {"commit": {"sha": "new-sha"}})
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

    def test_push_missing_file_404_creates(self):
        """GitCode's 404 for a missing file must be treated as 'create'."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})
            if method == "POST" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, {"commit": {"sha": "s"}})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        client.push("feed.dat", b"x")
        self.assertTrue(any(c[0] == "POST" for c in calls))

    def test_push_retries_transient_fork_race(self):
        """A 400 'cannot lock ref' right after forking is retried, then succeeds."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})  # missing -> create via POST
            if method == "POST" and endpoint.endswith("/contents/feed.dat"):
                if len([c for c in calls if c[0] == "POST"]) == 1:
                    resp = _Resp(400, {})
                    resp.text = '{"error_message":"git update-ref: cannot lock ref ..."}'
                    err = requests.exceptions.HTTPError("400 race")
                    err.response = resp
                    raise err
                return _Resp(200, {"commit": {"sha": "ok"}})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        with mock.patch("mycelium.interface.sower.gitcode.time.sleep"):
            attach(client, handler)
            result = client.push("feed.dat", b"x")

        posts = [c for c in calls if c[0] == "POST"]
        self.assertEqual(len(posts), 2)  # first raced, second succeeded
        self.assertEqual(result["commit"]["sha"], "ok")

    def test_push_does_not_retry_other_errors(self):
        """Only the fork-materialization race is retried; anything else raises."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})
            if method == "POST" and endpoint.endswith("/contents/feed.dat"):
                resp = _Resp(400, {})
                resp.text = '{"error_message":"some other problem"}'
                err = requests.exceptions.HTTPError("400")
                err.response = resp
                raise err
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        with mock.patch("mycelium.interface.sower.gitcode.time.sleep"):
            attach(client, handler)
            with self.assertRaises(requests.exceptions.HTTPError):
                client.push("feed.dat", b"x")

        posts = [c for c in calls if c[0] == "POST"]
        self.assertEqual(len(posts), 1)  # no retry for non-race errors


if __name__ == "__main__":
    unittest.main()
