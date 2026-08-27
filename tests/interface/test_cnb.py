"""
Unit tests for the sower interface ``CnbClient`` (the network layer is
mocked; these tests verify the request paths, parameters and logic
branches). Pulling is picker behavior, so only ``push`` is exercised.

CNB differs from Gitee/GitCode/GitHub in three ways covered here:
- repositories live inside organizations: ``group`` is optional in repo mode
  (when omitted, the organization is resolved from the profile username —
  username-named org when it exists, else an existing empty org is reused,
  else a username-named org is auto-created) and the namespace is the
  organization path, not the profile login;
- there is no contents write API: ``push`` writes via a real ``git push``
  (``_git`` is mocked; the temporary credential store is exercised for real);
- there is no fork API: ``fork`` mode parses the target name but raises
  whenever it is used.
"""

import os
import subprocess
import unittest
from unittest import mock

import requests

from mycelium.interface.sower.cnb import (
    CnbClient,
    _identity_ticket,
    _profile_username,
)
from mycelium.protocol import parse as parse_spore

_split_fork = CnbClient._split_fork  # classmethod under test


class _Resp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, status_code=200, data=None, headers=None):
        self.status_code = status_code
        self._data = data if data is not None else {}
        self.text = ""
        self.headers = headers or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.exceptions.HTTPError(f"{self.status_code} error")
            err.response = self
            raise err


class _Git:
    """Recorded stand-in for ``CnbClient._git`` (canned stdout)."""

    def __init__(self, stdout="a1b2c3"):
        self.calls = []
        self.stdout = stdout

    def __call__(self, cred, *args, cwd=None):
        self.calls.append((cred, args, cwd))
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=self.stdout + "\n"
        )


def make_client(**kwargs) -> CnbClient:
    """Build a client whose ``_request`` is replaced with a recording mock.

    The namespace is pre-seeded (when an explicit ``group`` is given) so
    unit tests skip the ``GET /user`` profile call; the auto-fetch and the
    group resolution (username org / empty-org reuse / auto-create) are
    covered by ``TestNamespace`` and the ``group=None`` tests.
    """
    defaults = dict(access_token="t", repo="my-feed", group="mycelium")
    defaults.update(kwargs)
    client = CnbClient(**defaults)
    if client.group is not None:
        client._namespace = client.group
    client._request = mock.Mock()
    return client


def attach(client: CnbClient, handler):
    """handler(method, endpoint, **kwargs) -> _Resp; emulates _request's raise_for_status."""

    def wrapped(method, endpoint, **kwargs):
        resp = handler(method, endpoint, **kwargs)
        resp.raise_for_status()
        return resp

    client._request.side_effect = wrapped


class TestSplitFork(unittest.TestCase):
    def test_bare_owner_repo(self):
        self.assertEqual(_split_fork("some/src"), ("some", "src"))

    def test_nested_owner(self):
        self.assertEqual(_split_fork("org/sub/src"), ("org/sub", "src"))

    def test_with_git_suffix(self):
        self.assertEqual(_split_fork("some/src.git"), ("some", "src"))

    def test_full_url(self):
        self.assertEqual(
            _split_fork("https://cnb.cool/some/src"), ("some", "src")
        )

    def test_nested_url(self):
        self.assertEqual(
            _split_fork("https://cnb.cool/org/sub/src"), ("org/sub", "src")
        )

    def test_domain_without_scheme(self):
        self.assertEqual(_split_fork("cnb.cool/some/src"), ("some", "src"))

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
    """repo/fork are mutually exclusive; repo mode makes the group optional."""

    def test_repo_mode(self):
        client = CnbClient("t", repo="my-feed", group="mycelium")
        self.assertEqual(client.repo, "my-feed")
        self.assertEqual(client.group, "mycelium")
        self.assertIsNone(client.fork)
        self.assertEqual(client.base_url, "https://api.cnb.cool")
        self.assertEqual(client.branch, "main")
        self.assertEqual(client.visibility, "public")

    def test_repo_mode_group_optional(self):
        """Without ``group`` the org is resolved lazily from the profile username."""
        client = CnbClient("t", repo="my-feed")
        self.assertEqual(client.repo, "my-feed")
        self.assertIsNone(client.group)

    def test_fork_mode_targets_source_name(self):
        client = CnbClient("t", fork="some/src")
        self.assertEqual(client.repo, "src")
        self.assertEqual(client.fork, "some/src")

    def test_fork_mode_accepts_nested_source(self):
        client = CnbClient("t", fork="https://cnb.cool/org/sub/stream.git")
        self.assertEqual(client.repo, "stream")

    def test_neither_repo_nor_fork_raises(self):
        with self.assertRaises(ValueError):
            CnbClient("t")

    def test_both_repo_and_fork_raise(self):
        with self.assertRaises(ValueError):
            CnbClient("t", repo="a", fork="b/c")

    def test_malformed_fork_raises(self):
        with self.assertRaises(ValueError):
            CnbClient("t", fork="no-slash-name")

    def test_bad_visibility_raises(self):
        for bad in ("open", "", "internal"):
            with self.assertRaises(ValueError):
                CnbClient("t", repo="a", group="g", visibility=bad)

    def test_git_author_default(self):
        client = CnbClient("t", repo="a", group="g")
        self.assertEqual(client._git_name, "Mycelium Sower")
        self.assertEqual(client._git_email, "sower@mycelium.local")

    def test_git_author_custom(self):
        client = CnbClient("t", repo="a", group="g", git_author="Horse <h@e.x>")
        self.assertEqual(client._git_name, "Horse")
        self.assertEqual(client._git_email, "h@e.x")

    def test_bad_git_author_raises(self):
        with self.assertRaises(ValueError):
            CnbClient("t", repo="a", group="g", git_author="no-angle-brackets")


class TestNamespace(unittest.TestCase):
    """The namespace is the organization path; the profile call validates the token."""

    def _client(self, profile, groups):
        """A no-group client with canned /user and /user/groups endpoints.

        ``groups=None`` simulates the missing ``account-engage`` scope
        (``GET /user/groups`` answers HTTP 403).
        """
        client = CnbClient("t", repo="my-feed")
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint))
            if endpoint == "/user":
                return _Resp(200, profile)
            if endpoint == "/user/groups":
                if groups is None:
                    return _Resp(403, {})  # account-engage scope missing
                return _Resp(200, groups)
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        client._request = mock.Mock()
        attach(client, handler)
        client._calls = calls
        return client

    def test_namespace_is_group(self):
        client = make_client()
        client._namespace = None
        client._request = mock.Mock(return_value=_Resp(200, {"username": "rainbow"}))
        self.assertEqual(client.namespace, "mycelium")
        client._request.assert_called_once_with("GET", "/user")

    def test_namespace_cached(self):
        client = make_client()
        client._namespace = None
        client._request = mock.Mock(return_value=_Resp(200, {}))
        _ = client.namespace
        _ = client.namespace
        self.assertEqual(client._request.call_count, 1)

    def test_without_group_uses_username_org_when_it_exists(self):
        """The username-named org wins over any other org (even non-empty)."""
        client = self._client(
            {"username": "rainbow"},
            [
                {"path": "rainbow", "sub_repo_count": 3},
                {"path": "empty", "sub_repo_count": 0},
            ],
        )
        self.assertEqual(client.namespace, "rainbow")
        self.assertEqual(client.group, "rainbow")
        self.assertIn(("GET", "/user/groups"), client._calls)

    def test_without_group_reuses_existing_empty_org(self):
        """No username-named org -> the first existing org with no repos is reused."""
        client = self._client(
            {"username": "rainbow"},
            [
                {"path": "busy", "sub_repo_count": 2},
                {"path": "spare", "sub_repo_count": 0},
                {"path": "spare2", "sub_repo_count": 0},
            ],
        )
        self.assertEqual(client.namespace, "spare")
        self.assertEqual(client.group, "spare")

    def test_without_group_no_empty_org_falls_back_to_username(self):
        """No username org and no empty org -> the username org (auto-created later)."""
        client = self._client(
            {"username": "rainbow"}, [{"path": "busy", "sub_repo_count": 2}]
        )
        self.assertEqual(client.namespace, "rainbow")
        self.assertEqual(client.group, "rainbow")

    def test_without_group_no_orgs_falls_back_to_username(self):
        client = self._client({"username": "rainbow"}, [])
        self.assertEqual(client.namespace, "rainbow")
        self.assertEqual(client.group, "rainbow")

    def test_without_group_missing_scope_degrades_to_username(self):
        """403 on /user/groups (no account-engage scope) -> username org only."""
        client = self._client({"username": "rainbow"}, None)
        self.assertEqual(client.namespace, "rainbow")
        self.assertEqual(client.group, "rainbow")

    def test_without_group_profile_lacks_username(self):
        client = CnbClient("t", repo="my-feed")
        client._request = mock.Mock(return_value=_Resp(200, {"nickname": "x"}))
        with self.assertRaises(ValueError):
            client.namespace

    def test_profile_username_helper(self):
        self.assertEqual(_profile_username({"username": "u"}), "u")
        with self.assertRaises(ValueError):
            _profile_username({})


class TestEnsureRepoExists(unittest.TestCase):
    def test_repo_exists_does_nothing(self):
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint))
            return _Resp(200, {"name": "my-feed"})

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())
        self.assertEqual(calls, [("GET", "/mycelium/my-feed")])

    def test_create_when_missing(self):
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/mycelium/my-feed":
                # 1st GET: existence check (404); later GETs: post-create polling (200)
                first = len([c for c in calls if c[0] == "GET" and c[1] == endpoint]) == 1
                return _Resp(404, {}) if first else _Resp(200, {"name": "my-feed"})
            if method == "GET" and endpoint == "/mycelium":
                return _Resp(200, {"path": "mycelium"})  # group exists
            if method == "POST" and endpoint == "/mycelium/-/repos":
                return _Resp(201, {})  # CNB answers with an empty body
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())

        post = next(c for c in calls if c[0] == "POST")
        self.assertEqual(post[1], "/mycelium/-/repos")
        body = post[2]["json"]
        self.assertEqual(body["name"], "my-feed")
        self.assertEqual(body["visibility"], "public")
        self.assertEqual(body["description"], "mycelium/my-feed")
        self.assertFalse(any(c[1] == "/groups" for c in calls))  # group existed

    def test_creates_group_when_missing(self):
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/mycelium/my-feed":
                first = len([c for c in calls if c[0] == "GET" and c[1] == endpoint]) == 1
                return _Resp(404, {}) if first else _Resp(200, {"name": "my-feed"})
            if method == "GET" and endpoint == "/mycelium":
                return _Resp(404, {})  # organization missing
            if method == "POST" and endpoint == "/groups":
                return _Resp(201, {})
            if method == "POST" and endpoint == "/mycelium/-/repos":
                return _Resp(201, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())

        create = next(c for c in calls if c[0] == "POST" and c[1] == "/groups")
        self.assertEqual(create[2]["json"]["path"], "mycelium")

    def test_creates_username_group_when_omitted(self):
        """No group -> org named after the profile username, created when missing."""
        client = make_client(group=None)
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/user":
                return _Resp(200, {"username": "rainbow"})
            if method == "GET" and endpoint == "/user/groups":
                return _Resp(200, [])  # no orgs to reuse
            if method == "GET" and endpoint == "/rainbow/my-feed":
                first = len([c for c in calls if c[0] == "GET" and c[1] == endpoint]) == 1
                return _Resp(404, {}) if first else _Resp(200, {"name": "my-feed"})
            if method == "GET" and endpoint == "/rainbow":
                return _Resp(404, {})  # username-named org missing
            if method == "POST" and endpoint == "/groups":
                return _Resp(201, {})
            if method == "POST" and endpoint == "/rainbow/-/repos":
                return _Resp(201, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())

        create = next(c for c in calls if c[0] == "POST" and c[1] == "/groups")
        self.assertEqual(create[2]["json"]["path"], "rainbow")
        self.assertEqual(client.group, "rainbow")
        self.assertEqual(sum(1 for c in calls if c[0] == "GET" and c[1] == "/user"), 1)

    def test_uses_existing_username_group_when_omitted(self):
        """No group -> an existing username-named org is used (no /groups creation)."""
        client = make_client(group=None)
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/user":
                return _Resp(200, {"username": "rainbow"})
            if method == "GET" and endpoint == "/user/groups":
                return _Resp(200, [{"path": "rainbow", "sub_repo_count": 2}])
            if method == "GET" and endpoint == "/rainbow/my-feed":
                first = len([c for c in calls if c[0] == "GET" and c[1] == endpoint]) == 1
                return _Resp(404, {}) if first else _Resp(200, {"name": "my-feed"})
            if method == "GET" and endpoint == "/rainbow":
                return _Resp(200, {"path": "rainbow"})
            if method == "POST" and endpoint == "/rainbow/-/repos":
                return _Resp(201, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())
        self.assertFalse(any(c[0] == "POST" and c[1] == "/groups" for c in calls))
        self.assertEqual(client.group, "rainbow")

    def test_reuses_existing_empty_group_when_omitted(self):
        """No group and no username org -> an existing empty org is reused."""
        client = make_client(group=None)
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/user":
                return _Resp(200, {"username": "rainbow"})
            if method == "GET" and endpoint == "/user/groups":
                return _Resp(200, [{"path": "spare", "sub_repo_count": 0}])
            if method == "GET" and endpoint == "/spare/my-feed":
                first = len([c for c in calls if c[0] == "GET" and c[1] == endpoint]) == 1
                return _Resp(404, {}) if first else _Resp(200, {"name": "my-feed"})
            if method == "GET" and endpoint == "/spare":
                return _Resp(200, {"path": "spare"})  # exists -> not created
            if method == "POST" and endpoint == "/spare/-/repos":
                return _Resp(201, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())
        self.assertFalse(any(c[0] == "POST" and c[1] == "/groups" for c in calls))
        self.assertEqual(client.group, "spare")

    def test_scope_missing_creates_username_group(self):
        """403 on /user/groups -> username-named org is created when missing."""
        client = make_client(group=None)
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/user":
                return _Resp(200, {"username": "rainbow"})
            if method == "GET" and endpoint == "/user/groups":
                return _Resp(403, {})  # account-engage scope missing
            if method == "GET" and endpoint == "/rainbow/my-feed":
                first = len([c for c in calls if c[0] == "GET" and c[1] == endpoint]) == 1
                return _Resp(404, {}) if first else _Resp(200, {"name": "my-feed"})
            if method == "GET" and endpoint == "/rainbow":
                return _Resp(404, {})
            if method == "POST" and endpoint == "/groups":
                return _Resp(201, {})
            if method == "POST" and endpoint == "/rainbow/-/repos":
                return _Resp(201, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        self.assertTrue(client.ensure_repo_exists())
        create = next(c for c in calls if c[0] == "POST" and c[1] == "/groups")
        self.assertEqual(create[2]["json"]["path"], "rainbow")

    def test_nested_group_not_auto_created(self):
        client = make_client(group="a/b")
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint == "/a/b/my-feed":
                return _Resp(404, {})
            if method == "GET" and endpoint == "/a/b":
                return _Resp(404, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        with self.assertRaises(ValueError):
            client.ensure_repo_exists()

    def test_fork_mode_raises(self):
        """CNB has no fork API: using fork mode raises with a manual-fork hint."""
        client = make_client(repo=None, fork="some/src")

        def handler(method, endpoint, **kwargs):
            return _Resp(404, {})  # target missing -> fork_repo is attempted

        attach(client, handler)
        with self.assertRaises(ValueError) as ctx:
            client.ensure_repo_exists()
        self.assertIn("manually", str(ctx.exception))

    def test_other_errors_raise(self):
        client = make_client()

        def handler(method, endpoint, **kwargs):
            return _Resp(500, {})

        attach(client, handler)
        with self.assertRaises(requests.exceptions.HTTPError):
            client.ensure_repo_exists()


class TestPush(unittest.TestCase):
    def test_push_creates_file(self):
        """Missing file -> 'Create file ...' message; git flow runs to a push."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})  # missing file
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        git = _Git(stdout="new-sha")
        client._git = git
        result = client.push("feed.dat", b"hello")

        self.assertEqual(result["commit"]["sha"], "new-sha")
        self.assertEqual(result["message"], "Create file feed.dat")

        # The git flow: clone, (branch check), identity, add, commit, push.
        commands = [args for _, args, _ in git.calls]
        self.assertEqual(commands[0][:2], ("clone", "https://cnb.cool/mycelium/my-feed"))
        self.assertIn(("commit", "-m", "Create file feed.dat"), commands)
        push_call = next(args for args in commands if args[0] == "push")
        self.assertEqual(push_call[-1], "HEAD:main")

    def test_push_updates_file(self):
        """Existing file -> 'Update file ...' message; sha lookup succeeded."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, {"type": "blob", "sha": "old-sha"})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        git = _Git()
        client._git = git
        client.push("feed.dat", b"world")

        commands = [args for _, args, _ in git.calls]
        self.assertIn(("commit", "-m", "Update file feed.dat"), commands)

    def test_push_custom_commit_message(self):
        client = make_client()

        def handler(method, endpoint, **kwargs):
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(200, {"type": "blob", "sha": "s"})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        git = _Git()
        client._git = git
        client.push("feed.dat", b"x", commit_message="publish v1")
        commands = [args for _, args, _ in git.calls]
        self.assertIn(("commit", "-m", "publish v1"), commands)

    def test_push_credential_file_created_and_removed(self):
        client = make_client()

        def handler(method, endpoint, **kwargs):
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        git = _Git()
        client._git = git
        client.push("feed.dat", b"x")

        cred = git.calls[0][0]  # the credential file path passed to _git
        self.assertFalse(os.path.exists(cred), "credential store must be deleted")

    def test_credential_file_holds_cnb_token(self):
        client = make_client()
        path = client._write_credential_file()
        try:
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "https://cnb:t@cnb.cool\n")
        finally:
            os.unlink(path)

    def test_push_writes_content_bytes(self):
        """The pushed blob must be the raw bytes, written into the clone."""
        client = make_client()

        def handler(method, endpoint, **kwargs):
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        git = _Git()
        client._git = git

        def fake_git(cred, *args, cwd=None):
            git(cred, *args, cwd=cwd)
            if args[0] == "add":
                # Capture the blob while the clone still exists (the temp
                # directory is removed when push() returns).
                git.blob = open(os.path.join(cwd, "feed.dat"), "rb").read()
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="s\n")

        client._git = fake_git
        client.push("feed.dat", b"\x00\x01binary")
        self.assertEqual(git.blob, b"\x00\x01binary")

    def test_push_retries_transient_git_failure(self):
        """A git failure mentioning a fresh-repo race is retried, then succeeds."""
        client = make_client()

        def handler(method, endpoint, **kwargs):
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        state = {"n": 0}

        def flaky_git(cred, *args, cwd=None):
            state["n"] += 1
            if state["n"] == 1 and args[0] == "clone":
                raise subprocess.CalledProcessError(
                    128, args, stderr="fatal: repository 'x' not found"
                )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="s\n")

        client._git = flaky_git
        with mock.patch("mycelium.interface.sower.cnb.time.sleep"):
            result = client.push("feed.dat", b"x")

        self.assertEqual(result["commit"]["sha"], "s")
        self.assertGreaterEqual(state["n"], 2)

    def test_push_does_not_retry_other_git_failures(self):
        client = make_client()

        def handler(method, endpoint, **kwargs):
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        state = {"n": 0}

        def bad_git(cred, *args, cwd=None):
            state["n"] += 1
            raise subprocess.CalledProcessError(128, args, stderr="fatal: authentication failed")

        client._git = bad_git
        with mock.patch("mycelium.interface.sower.cnb.time.sleep"):
            with self.assertRaises(subprocess.CalledProcessError):
                client.push("feed.dat", b"x")

        self.assertEqual(state["n"], 1)  # no retry for non-transient errors

    def test_push_resolves_username_group_for_remote(self):
        """No group -> the git remote uses the resolved organization."""
        client = make_client(group=None)

        def handler(method, endpoint, **kwargs):
            if method == "GET" and endpoint == "/user":
                return _Resp(200, {"username": "rainbow"})
            if method == "GET" and endpoint == "/user/groups":
                return _Resp(200, [{"path": "spare", "sub_repo_count": 0}])
            if method == "GET" and endpoint.endswith("/contents/feed.dat"):
                return _Resp(404, {})
            raise AssertionError(f"unexpected call: {method} {endpoint}")

        attach(client, handler)
        git = _Git()
        client._git = git
        client.push("feed.dat", b"x")

        commands = [args for _, args, _ in git.calls]
        self.assertEqual(commands[0][:2], ("clone", "https://cnb.cool/spare/my-feed"))
        self.assertEqual(client.group, "spare")


class TestExistingSha(unittest.TestCase):
    def _client(self, data):
        client = make_client()
        client._request = mock.Mock(return_value=_Resp(200, data))
        return client

    def test_blob_sha(self):
        client = self._client({"type": "blob", "sha": "abc"})
        self.assertEqual(client._existing_sha("/x"), "abc")

    def test_empty_repo_means_missing(self):
        client = self._client({"type": "empty", "sha": ""})
        self.assertIsNone(client._existing_sha("/x"))

    def test_404_means_missing(self):
        client = make_client()
        err = requests.exceptions.HTTPError("404")
        err.response = _Resp(404, {})
        client._request = mock.Mock(side_effect=err)
        self.assertIsNone(client._existing_sha("/x"))

    def test_directory_raises(self):
        client = self._client({"type": "tree", "entries": []})
        with self.assertRaises(ValueError):
            client._existing_sha("/x")


class TestRawUrlAndSporeLink(unittest.TestCase):
    def test_raw_url(self):
        client = make_client()
        self.assertEqual(
            client.raw_url("feed.dat"),
            "https://api.cnb.cool/mycelium/my-feed/-/git/raw/main/feed.dat",
        )

    def test_raw_url_nested_path(self):
        client = make_client()
        self.assertEqual(
            client.raw_url("dir/feed.dat"),
            "https://api.cnb.cool/mycelium/my-feed/-/git/raw/main/dir/feed.dat",
        )

    def test_spore_link_round_trip(self):
        client = make_client()
        vk = bytes(range(32))
        link = client.spore_link("feed.dat", vk)
        spore = parse_spore(link)
        self.assertEqual(spore.host, "api.cnb.cool")
        self.assertEqual(spore.path, "mycelium/my-feed/-/git/raw/main/feed.dat")
        self.assertEqual(spore.vk, vk)


class TestDeleteRepo(unittest.TestCase):
    def test_delete(self):
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            return _Resp(204, {})

        attach(client, handler)
        client.delete_repo()
        self.assertEqual(calls[0][0], "DELETE")
        self.assertEqual(calls[0][1], "/mycelium/my-feed")

    def test_delete_with_identity_ticket_retry(self):
        """A refused first attempt carrying a ticket is retried with it."""
        client = make_client()
        calls = []

        def handler(method, endpoint, **kwargs):
            calls.append((method, endpoint, kwargs))
            if len(calls) == 1:
                return _Resp(403, {"identity_ticket": "tkt-123"})
            return _Resp(204, {})

        attach(client, handler)
        client.delete_repo()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][2]["headers"]["X-Cnb-Identity-Ticket"], "tkt-123")

    def test_delete_refusal_without_ticket_propagates(self):
        client = make_client()

        def handler(method, endpoint, **kwargs):
            return _Resp(412, {"errcode": 9, "errmsg": "root group management rules"})

        attach(client, handler)
        with self.assertRaises(requests.exceptions.HTTPError):
            client.delete_repo()


class TestIdentityTicket(unittest.TestCase):
    def test_header_ticket(self):
        resp = _Resp(403, {}, headers={"X-Cnb-Identity-Ticket": "h"})
        self.assertEqual(_identity_ticket(resp), "h")

    def test_json_ticket(self):
        resp = _Resp(403, {"identity_ticket": "j"})
        self.assertEqual(_identity_ticket(resp), "j")

    def test_no_ticket(self):
        self.assertIsNone(_identity_ticket(_Resp(412, {})))
        self.assertIsNone(_identity_ticket(None))


if __name__ == "__main__":
    unittest.main()
