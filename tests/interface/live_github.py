"""
Live smoke test for the publisher (GithubClient) against the real GitHub API.
Not collected by pytest; run manually, the token comes from argv or from
the development-period test token in tests/interface/tokens.py:

    python tests/interface/live_github.py [<access_token>]

Flow:
    1. Read the default branch of the fork source (octocat/Hello-World);
    2. Fork mode: GithubClient(fork="octocat/Hello-World") -> same-named
       repo <login>/Hello-World, where <login> is resolved from the
       authorized user's profile (GET /user) — there is no owner parameter.
       The repo is created on first run, reused on later runs; a
       pre-existing *non-fork* repo with that name aborts the test;
    3. Push an encrypted sclerotium via the publisher interface
       (GithubClient.push); pulling is subscriber behavior, so the
       round-trip is verified through the subscriber interface
       (Hypha.pull) instead of a client-side pull;
    4. The spore link is built through the jsDelivr CDN (``cdn=True`` is
       hardcoded; cdn.jsdelivr.net/gh/...) and pulled anonymously — this
       also exercises the ``cdn`` acceleration path end to end;
    5. Verify the repository name equals the source name (Hello-World);
    6. Cleanup: delete the forked repo only when this run actually created
       it; reused repositories are left in place.

Note: GitHub may be unreachable from some regions without a proxy/CDN;
the raw host is fetched through the jsDelivr mirror (``cdn=True``), so the
subscriber-side pull works as long as cdn.jsdelivr.net is reachable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

# tests/interface/ -> project root is three levels up.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mycelium import crypto  # noqa: E402
from mycelium.interface.sower import GithubClient  # noqa: E402
from mycelium.interface.picker import Hypha  # noqa: E402
from mycelium.protocol import Sclerotium  # noqa: E402

TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""
if not TOKEN:
    # Fall back to the development-period test token (tests/interface/tokens.py).
    try:
        from tests.interface.tokens import GITHUB_TOKEN as TOKEN
    except ImportError:
        pass
if not TOKEN:
    sys.exit("usage: python tests/interface/live_github.py <access_token>")

# Fork source (the disguise object): a public repo that allows forking.
SRC_OWNER, SRC_REPO = "octocat", "Hello-World"
TARGET = SRC_REPO  # same-name fork: the target keeps the source's name
owner: str | None = None
created_this_run = False


def cleanup() -> None:
    global created_this_run
    if not created_this_run:
        print(
            f"  [cleanup] {owner}/{TARGET} was reused (not created this run) "
            "- left in place"
        )
        return
    try:
        GithubClient(TOKEN, repo=TARGET).delete_repo()
        print(f"  [cleanup] deleted {owner}/{TARGET}")
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        print(f"  [cleanup] delete {owner}/{TARGET} -> HTTP {code} (ignored)")


def main() -> None:
    global owner, created_this_run
    src_info = requests.get(
        f"https://api.github.com/repos/{SRC_OWNER}/{SRC_REPO}",
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=30,
    )
    src_info.raise_for_status()
    branch = src_info.json().get("default_branch") or "main"
    print(f"[1] fork source: {SRC_OWNER}/{SRC_REPO} (default branch: {branch})")

    dst = GithubClient(
        TOKEN,
        fork=f"{SRC_OWNER}/{SRC_REPO}",
        branch=branch,
        cdn=True,  # hardcoded: exercise the jsDelivr acceleration path
        poll_interval=2.0,
        max_poll=30,
    )
    # The account login comes from the API profile (GET /user); there is no
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
    print("[4] pushed encrypted sclerotium via GithubClient.push")

    # The round-trip is verified through the *subscriber* interface. The
    # jsDelivr CDN (cdn=True) accelerates the raw host; pull anonymously.
    link = dst.spore_link("feed.dat", cfg.vk)
    print("    spore link (jsDelivr CDN):", link)
    fetched = Hypha().pull(link)
    assert fetched.content == sclerotium.content, "content mismatch"
    assert len(fetched) == len(sclerotium), "fruit count mismatch"
    print("[4] pulled + verified via Hypha.pull (subscriber interface)")

    info = dst._request("GET", f"/repos/{owner}/{TARGET}").json()
    assert info["name"] == TARGET, f"name mismatch: {info.get('name')!r}"
    print(f"[5] repo name confirmed: {info['name']}")

    print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
