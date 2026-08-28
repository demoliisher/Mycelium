"""
Unit tests for the sower interface ``GithubClient`` (the network layer
is mocked; these tests verify the request paths, parameters and logic
branches). Pulling is picker behavior, so only ``push`` is exercised.

GitHub differs from Gitee/GitCode in three ways covered here:
- authentication goes through an ``Authorization: Bearer`` header, not an
  ``access_token`` query parameter;
- the contents API uses a single PUT endpoint for both create and update;
- a fork materializes asynchronously, and a write right after forking can
  transiently fail with HTTP 409/422 (retried briefly).
"""

import base64
import unittest
from unittest import mock

import requests

from mycelium.interface.sower.github import GithubClient, _jsdelivr_cdn

_split_fork = GithubClient._split_fork  # classmethod under test


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


def make_client(**kwargs) -> GithubClient:
    """Build a client whose ``_request`` is replaced with a recording mock.

    The namespace is pre-seeded so unit tests skip the ``GET /user`` profile
    call; the auto-fetch itself is covered by ``TestNamespace``. ``cdn=True``
    is hardcoded so the tests exercise the jsDelivr acceleration path.
    """
    defaults = dict(access_token="t", repo="my-feed", cdn=True)
    defaults.update(kwargs)
    client = GithubClient(**defaults)
    client._namespace = "rainbow"
    client._request = mock.Mock()
    return client


def attach(client: GithubClient, handler):
    """handler(method, endpoint, **kwargs) -> _Resp; emulates _request's raise_for_status."""

    def wrapped(method, endpoint, **kwargs):
        resp = handler(method, endpoint, **kwargs)
        resp.raise_for_status()
        return resp

    client._request.side_effect = wrapped


class TestJsdelivrCdn(unittest.TestCase):
    def test_rewrites_raw_url(self):
        self.assertEqual(
            _jsdelivr_cdn(
                "https://raw.githubusercontent.com/alice/my-feed/main/feed.dat"
            ),
            "https://cdn.jsdelivr.net/gh/alice/my-feed@main/feed.dat",
        )

    def test_preserves_nested_path(self):
        self.assertEqual(
            _jsdelivr_cdn(
                "https://raw.githubusercontent.com/alice/my-feed/main/data/feed.dat"
            ),
            "https://cdn.jsdelivr.net/gh/alice/my-feed@main/data/feed.dat",
        )

    def test_non_raw_url_unchanged(self):
        url = "https://api.github.com/repos/alice/my-feed"
        self.assertEqual(_jsdelivr_cdn(url), url)

    def test_private_repo_style_branch(self):
        self.assertEqual(
            _jsdelivr_cdn(
                "https://raw.githubusercontent.com/alice/my-feed/dev/feed.dat"
            ),
            "https://cdn.jsdelivr.net/gh/alice/my-feed@dev/feed.dat",
        )


class TestSplitFork(unittest.TestCase):
    def test_bare_owner_repo(self):
        self.assertEqual(_split_fork("some/src"), ("some", "src"))

    def test_with_git_suffix(self):
        self.assertEqual(_split_fork("some/src.git"), ("some", "src"))

    def test_full_url(self):
        self.assertEqual(
            _split_fork("https://github.com/some/src"), ("some", "src")
        )

    def test_full_url_with_git(self):
        self.assertEqual(
            _split_fork("https://github.com/some/src.git"), ("some", "src")
        )

    def test_domain_without_scheme(self):
        self.assertEqual(_split_fork("github.com/some/src"), ("some", "src"))

    def test_trailing_slash(self):
        self.assertEqual(_split_fork("some/src/"), ("some", "src"))

    def test_bare_name_raises(self):
        with self.assertRaises(ValueError):
            _split_fork("just-a-name")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            _split_fork("")

    def test_cross_platform_url_raises(self):
        for bad in ("https://gitee.com/some/src", "https://gitcode.com/some/src"):
            with self.assertRaises(ValueError):
                _split_fork(bad)

    def test_ssh_style_raises(self):
        with self.assertRaises(ValueError):
            _split_fork("git@github.com:some/src.git")


class TestConstructor(unittest.TestCase):
    """repo/fork are mutually exclusive; fork mode targets the source name."""

    def test_repo_mode(self):
        client = GithubClient("t", repo="my-feed")
        self.assertEqual(client.repo, "my-feed")
        self.assertIsNone(client.fork)
        self.assertEqual(client.branch, "main")

    def test_cdn_defaults_to_raw(self):
        client = GithubClient("t", repo="my-feed")
        self.assertIsNone(client.cdn)

    def test_cdn_true_uses_jsdelivr(self):
        client = GithubClient("t", repo="my-feed", cdn=True)
        self.assertIs(client.cdn, _jsdelivr_cdn)

    def test_cdn_false_disables_acceleration(self):
        client = GithubClient("t", repo="my-feed", cdn=False)
        self.assertIsNone(client.cdn)

    def test_cdn_invalid_raises(self):
        with self.assertRaises(TypeError):
            GithubClient("t", repo="my-feed", cdn="mirror")

    def test_cdn_custom_callable(self):
        def passthrough(url):
            return url.upper()

        client = GithubClient("t", repo="my-feed", cdn=passthrough)
        self.assertEqual(client.cdn("abc"), "ABC")

    def test_fork_mode_targets_source_name(self):
        client = GithubClient("t", fork="some/src")
        self.assertEqual(client.repo, "src")
        self.assertEqual(client.fork, "some/src")

    def test_fork_mode_with_url(self):
        client = GithubClient("t", fork="https://github.com/up/stream.git")
        self.assertEqual(client.repo, "stream")

    def test_neither_repo_nor_fork_raises(self):
        with self.assertRaises(ValueError):
            GithubClient("t")

    def test_both_repo_and_fork_raise(self):
        with self.assertRaises(ValueError):
            GithubClient("t", repo="a", fork="b/c")

    def test_malformed_fork_raises(self):
        with self.assertRaises(ValueError):
            GithubClient("t", fork="no-slash-name")

    def test_cross_platform_fork_raises(self):
        for bad in ("https://gitee.com/a/b", "git@gitlab.com:a/b.git"):
            with self.assertRaises(ValueError):
                GithubClient("t", fork=bad)


class TestNamespace(unittest.TestCase):
    """The account login is fetched from the API profile, not user input."""

    def test_namespace_fetched_from_user_profile(self):
        client = GithubClient("t", repo="my-feed")
        client._request = mock.Mock(return_value=_Resp(200, {"login": "alice"}))
        self.assertEqual(client.namespace, "alice")
        client._request.assert_called_once_with("GET", "/user")

    def test_namespace_cached(self):
        client = GithubClient("t", repo="my-feed")
        client._request = mock.Mock(return_value=_Resp(200, {"login": "alice"}))
        _ = client.namespace
        _ = client.namespace
        self.assertEqual(client._request.call_count, 1)

    def test_namespace_missing_login_raises(self):
        client = GithubClient("t", repo="my-feed")
        client._request = mock.Mock(return_value=_Resp(200, {}))
        with self.assertRaises(ValueError):
            _ = client.namespace


class TestAuth(unittest.TestCase):
    """GitHub authenticates via an Authorization: Bearer header."""

    def test_bearer_header_attached(self):
        client = GithubClient("secret-token", repo="my-feed")
        client.session = mock.Mock()
        client.session.request.return_value = _Resp(200, {"login": "alice"})
        client._request("GET", "/user")
        _, kwargs = client.session.request.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret-token")
        self.assertNotIn("access_token", kwargs.get("params", {}))


class TestEnsureRepoExists(unittest.TestCase):
    def test_repo_exists_does_nothing(self):
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint))
            return _Resp(200, {"name": "my-feed"})

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
                return _Resp(404, {}) if first else _Resp(200, {"name": "my-feed"})
            if method == "POST" and endpoint == "/user/repos":
                return _Resp(201, {"name": "my-feed", "full_name": "rainbow/my-feed"})
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
        """Fork mode: target missing -> fork the source under its own name."""
        client = make_client(repo=None, fork="some/src")
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/repos/rainbow/src":
                # 1st GET: existence check (404); later GETs: post-fork polling (200)
                first = len([c for c in calls if c[0] == "GET" and c[1] == endpoint]) == 1
                return _Resp(404, {}) if first else _Resp(200, {"name": "src"})
            if method == "POST" and endpoint == "/repos/some/src/forks":
                return _Resp(202, {"name": "src", "full_name": "rainbow/src"})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())

        self.assertEqual(client.repo, "src")  # target keeps the source name
        post = next(c for c in calls if c[0] == "POST")
        self.assertEqual(post[1], "/repos/some/src/forks")

    def test_fork_reuses_existing(self):
        """Fork mode: same-named repo already exists -> reuse, no fork call."""
        client = make_client(repo=None, fork="some/src")
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/repos/rainbow/src":
                return _Resp(200, {"name": "src"})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())
        self.assertFalse(any(c[0] == "POST" for c in calls))

    def test_fork_with_url_source(self):
        client = make_client(repo=None, fork="https://github.com/up/stream.git")
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/repos/rainbow/stream":
                return _Resp(404, {}) if len(calls) == 1 else _Resp(200, {"name": "stream"})
            if method == "POST" and endpoint == "/repos/up/stream/forks":
                return _Resp(202, {"name": "stream", "full_name": "rainbow/stream"})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())

        self.assertEqual(client.repo, "stream")
        posts = [c for c in calls if c[0] == "POST"]
        self.assertEqual(posts[0][1], "/repos/up/stream/forks")

    def test_other_errors_raise(self):
        client = make_client()

        def handler(method, endpoint, **kwargs):
            return _Resp(500, {})

        attach(client, handler)
        with self.assertRaises(requests.exceptions.HTTPError):
            client.ensure_repo_exists()


class TestPush(unittest.TestCase):
    def test_push_creates_file(self):
        """File missing (HTTP 404) -> create via PUT, no sha."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})  # GitHub replies 404 for a missing file
            if method == "PUT" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(201, {"content": {"sha": "new-sha"}})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        result = client.push("feed.dat", b"hello")

        put = next(c for c in calls if c[0] == "PUT")
        payload = put[2]["json"]
        self.assertNotIn("sha", payload)
        self.assertEqual(payload["message"], "Create file feed.dat")
        self.assertEqual(payload["branch"], "main")
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

    def test_push_retries_fork_race(self):
        """A transient 409 'Git Repository is empty' right after forking is retried."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})  # missing -> create
            if method == "PUT" and endpoint.endswith("/contents/feed.dat"):
                if len([c for c in calls if c[0] == "PUT"]) < 3:
                    resp = _Resp(409, {})
                    resp.text = '{"message":"Git Repository is empty."}'
                    return resp
                return _Resp(201, {"content": {"sha": "new-sha"}})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        with mock.patch("mycelium.interface.sower.github.time.sleep"):
            result = client.push("feed.dat", b"x")

        puts = [c for c in calls if c[0] == "PUT"]
        self.assertEqual(len(puts), 3)  # 2 transient failures + 1 success
        self.assertEqual(result["content"]["sha"], "new-sha")

    def test_push_retries_422_repository_error(self):
        """A transient 422 mentioning the repository is retried as well."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})
            if method == "PUT" and endpoint.endswith("/contents/feed.dat"):
                if len([c for c in calls if c[0] == "PUT"]) < 2:
                    resp = _Resp(422, {})
                    resp.text = '{"message":"Repository is empty."}'
                    return resp
                return _Resp(201, {"content": {"sha": "s"}})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        with mock.patch("mycelium.interface.sower.github.time.sleep"):
            client.push("feed.dat", b"x")
        self.assertEqual(len([c for c in calls if c[0] == "PUT"]), 2)

    def test_push_non_race_error_propagates(self):
        """A 422 that does not mention the repository must propagate without retry.

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
                return _Resp(404, {})
            if method == "PUT" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(422, {"message": "ref is not valid"})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        with mock.patch("mycelium.interface.sower.github.time.sleep"):
            with self.assertRaises(requests.exceptions.HTTPError):
                client.push("feed.dat", b"x")

        puts = [c for c in calls if c[0] == "PUT"]
        self.assertEqual(len(puts), 1)  # no retry on unrelated errors


class TestSporeLink(unittest.TestCase):
    def test_raw_url(self):
        client = make_client()
        self.assertEqual(
            client.raw_url("feed.dat"),
            "https://raw.githubusercontent.com/rainbow/my-feed/main/feed.dat",
        )

    def test_raw_url_nested_path(self):
        client = make_client()
        self.assertEqual(
            client.raw_url("data/feed.dat"),
            "https://raw.githubusercontent.com/rainbow/my-feed/main/data/feed.dat",
        )

    def test_spore_link_jsdelivr(self):
        # make_client hardcodes cdn=True, so the link is jsDelivr-accelerated.
        client = make_client()
        link = client.spore_link("feed.dat", b"k" * 32)
        from mycelium.protocol import parse as parse_spore

        spore = parse_spore(link)
        self.assertEqual(spore.host, "cdn.jsdelivr.net")
        self.assertEqual(spore.path, "gh/rainbow/my-feed@main/feed.dat")

    def test_spore_link_no_cdn(self):
        client = make_client(cdn=False)
        link = client.spore_link("feed.dat", b"k" * 32)
        from mycelium.protocol import parse as parse_spore

        spore = parse_spore(link)
        self.assertEqual(spore.host, "raw.githubusercontent.com")
        self.assertEqual(spore.path, "rainbow/my-feed/main/feed.dat")

    def test_spore_link_custom_cdn(self):
        def custom(url):
            return url.replace("raw.githubusercontent.com", "mirror.example.com")

        client = make_client(cdn=custom)
        link = client.spore_link("feed.dat", b"k" * 32)
        from mycelium.protocol import parse as parse_spore

        spore = parse_spore(link)
        self.assertEqual(spore.host, "mirror.example.com")
        self.assertEqual(spore.path, "rainbow/my-feed/main/feed.dat")


class TestGitBackup(unittest.TestCase):
    """The git-push backup mode: identity resolution and the fallback path."""

    def _client(self, profile, emails=None, emails_status=200):
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint))
            if method == "GET" and endpoint == "/user":
                return _Resp(200, profile)
            if method == "GET" and endpoint == "/user/emails":
                return _Resp(emails_status, emails if emails is not None else {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        client._calls = calls
        return client

    def test_identity_profile_email_wins(self):
        client = self._client({"login": "rainbow", "email": "me@x"})
        self.assertEqual(client._git_identity(), ("rainbow", "me@x"))
        self.assertNotIn(("GET", "/user/emails"), client._calls)

    def test_identity_primary_email_from_emails_endpoint(self):
        client = self._client(
            {"login": "rainbow", "email": ""},
            [{"email": "a@x", "primary": False}, {"email": "b@x", "primary": True}],
        )
        self.assertEqual(client._git_identity(), ("rainbow", "b@x"))

    def test_identity_noreply_fallback(self):
        client = self._client({"login": "rainbow", "id": 42}, emails_status=403)
        self.assertEqual(
            client._git_identity(),
            ("rainbow", "42+rainbow@users.noreply.github.com"),
        )

    def test_identity_profile_403_returns_none(self):
        client = make_client()
        client._request = mock.Mock(
            side_effect=requests.exceptions.HTTPError("403")
        )
        self.assertIsNone(client._git_identity())

    def test_identity_no_login_returns_none(self):
        client = self._client({"email": "x"})
        self.assertIsNone(client._git_identity())

    def test_remote_uses_x_access_token(self):
        client = make_client()
        self.assertEqual(
            client._git_remote(),
            ("https://github.com/rainbow/my-feed", "x-access-token", "t"),
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
                return _Resp(404, {})
            if method == "PUT" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(500, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        with mock.patch(
            "mycelium.interface.sower.base.GitPusher"
        ) as pusher_cls, mock.patch(
            "mycelium.interface.sower.github.time.sleep"
        ):
            pusher = pusher_cls.return_value
            pusher.push_file.return_value = {"commit": {"sha": "g"}}
            result = client.push("feed.dat", b"x")

        self.assertEqual(result["commit"]["sha"], "g")
        pusher_cls.assert_called_once_with(
            "https://github.com/rainbow/my-feed",
            "x-access-token",
            "t",
            timeout=300.0,
        )
        pusher.push_file.assert_called_once_with(
            "main", "feed.dat", b"x", "Create file feed.dat", "rainbow", "me@x"
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
                return _Resp(404, {})
            if method == "PUT" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(500, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        with mock.patch(
            "mycelium.interface.sower.base.GitPusher"
        ) as pusher_cls, mock.patch(
            "mycelium.interface.sower.github.time.sleep"
        ):
            with self.assertRaises(requests.exceptions.HTTPError):
                client.push("feed.dat", b"x")
        pusher_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
