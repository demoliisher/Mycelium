"""
Live smoke test for the publisher (GiteeClient) against the real Gitee API.
Not collected by pytest; run manually, the token comes from argv or from
the development-period test token in tests/interface/tokens.py:

    python tests/interface/live_gitee.py [<access_token>]

Flow:
    1. Read the default branch of the fork source (pandao/editor.md);
    2. Fork mode: GiteeClient(fork="pandao/editor.md") -> same-named repo
       <namespace>/editor.md, where namespace (个人空间) is resolved from the
       authorized user's profile (GET /user) — there is no owner parameter.
       The repo is created on first run, reused on later runs; a
       pre-existing *non-fork* repo with that name aborts the test;
    3. Push an encrypted sclerotium via the publisher interface (GiteeClient.push);
       pulling is subscriber behavior, so the round-trip is verified through
       the subscriber interface (Hypha.pull) instead of a client-side pull;
    4. Verify the repository path/name equal the source name (editor.md);
    5. Cleanup: delete the forked repo only when this run actually created
       it; reused repositories are left in place.

Note: Gitee forbids forking repositories you already own (the fork would
collide with the source name), so a third-party public repository is used
as the source -- which is also the real "disguise" use case.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

# tests/interface/ -> project root is three levels up.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mycelium import crypto  # noqa: E402
from mycelium.interface.sower import GiteeClient  # noqa: E402
from mycelium.interface.picker import Hypha  # noqa: E402
from mycelium.protocol import Sclerotium, Spore  # noqa: E402

TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""
if not TOKEN:
    # Fall back to the development-period test token (tests/interface/tokens.py).
    try:
        from tests.interface.tokens import GITEE_TOKEN as TOKEN
    except ImportError:
        pass
if not TOKEN:
    sys.exit("usage: python tests/interface/live_gitee.py <access_token>")

# Fork source (the disguise object): a third-party public repo that allows forking.
SRC_OWNER, SRC_REPO = "pandao", "editor.md"
TARGET = SRC_REPO  # same-name fork: the target keeps the source's name
owner: str | None = None
created_this_run = False


class _TokenSession(requests.Session):
    """Attach the access token to every GET (the private-repo raw API needs it)."""

    def __init__(self, token: str):
        super().__init__()
        self._token = token

    def get(self, url, **kwargs):  # noqa: ANN001 - requests get(**kwargs)
        params = dict(kwargs.pop("params", None) or {})
        params["access_token"] = self._token
        return super().get(url, params=params, **kwargs)


def cleanup() -> None:
    global created_this_run
    if not created_this_run:
        print(
            f"  [cleanup] {owner}/{TARGET} was reused (not created this run) "
            "- left in place"
        )
        return
    try:
        GiteeClient(TOKEN, repo=TARGET).delete_repo()
        print(f"  [cleanup] deleted {owner}/{TARGET}")
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        print(f"  [cleanup] delete {owner}/{TARGET} -> HTTP {code} (ignored)")


def main() -> None:
    global owner, created_this_run
    src_info = requests.get(
        f"https://gitee.com/api/v5/repos/{SRC_OWNER}/{SRC_REPO}",
        params={"access_token": TOKEN},
        timeout=30,
    )
    src_info.raise_for_status()
    branch = src_info.json().get("default_branch") or "master"
    print(f"[1] fork source: {SRC_OWNER}/{SRC_REPO} (default branch: {branch})")

    dst = GiteeClient(
        TOKEN,
        fork=f"{SRC_OWNER}/{SRC_REPO}",
        branch=branch,
        poll_interval=1.0,
        max_poll=30,
    )
    # The personal space comes from the API profile (GET /user); there is no
    # owner parameter. Accessing it also validates the token.
    owner = dst.namespace
    print(f"[2] token OK, namespace = {owner}")

    existed = dst._repo_exists()
    if existed:
        info = dst._request("GET", f"/repos/{owner}/{TARGET}").json()
        if not info.get("fork"):
            raise SystemExit(
                f"aborting: {owner}/{TARGET} already exists but is NOT a fork; "
                "refusing to push into a real repository. Delete or rename it first."
            )
    assert dst.ensure_repo_exists() is True
    created_this_run = not existed
    print(
        f"[3] fork mode {SRC_OWNER}/{SRC_REPO} -> {owner}/{TARGET} "
        f"({'created' if created_this_run else 'reused'})"
    )

    # Publisher pushes an encrypted sclerotium.
    cfg = crypto.new()
    sclerotium = Sclerotium.new("Live Smoke")
    sclerotium.entry("hello v1")
    dst.push("feed.dat", sclerotium.encrypt(cfg), commit_message="publish v1")
    print("[4] pushed encrypted sclerotium via GiteeClient.push")

    # The round-trip is verified through the *subscriber* interface: build
    # the spore link (private repo -> API raw endpoint + token session) and
    # pull it with Hypha.
    raw_path = f"api/v5/repos/{owner}/{TARGET}/raw/feed.dat?ref={branch}"
    link = Spore("gitee.com", raw_path, cfg.vk).export()
    fetched = Hypha(session=_TokenSession(TOKEN)).pull(link)
    assert fetched.content == sclerotium.content, "content mismatch"
    assert len(fetched) == len(sclerotium), "fruit count mismatch"
    print("[4] pulled + verified via Hypha.pull (subscriber interface)")

    info = dst._request("GET", f"/repos/{owner}/{TARGET}").json()
    assert info["path"] == TARGET, f"path mismatch: {info.get('path')!r}"
    assert info["name"] == TARGET, f"name mismatch: {info.get('name')!r}"
    print(f"[5] repo path/name confirmed: {info['path']} / {info['name']}")

    print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
