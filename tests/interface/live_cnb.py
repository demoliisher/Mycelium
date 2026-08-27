"""
Live smoke test for the sower (CnbClient) against the real cnb.cool API.
Not collected by pytest; run manually, the token comes from argv or from
the development-period test token in tests/interface/tokens.py:

    python tests/interface/live_cnb.py [<access_token>]

Flow:
    1. CnbClient(token, repo="<fresh>", group="mycelium-cnb-probe") -> the
       target is <group>/<repo>; the organization is NOT auto-created here
       because CNB limits root-organization creation to a yearly quota and
       the probe organization already exists (the auto-create path itself is
       exercised by the unit tests and was verified manually);
    1b. A group-less client resolves the organization from the profile
       username (no organization is created by this step — creation is
       quota-limited and covered by the unit tests; an existing empty
       organization would be reused instead);
    2. ensure_repo_exists() creates the repository (created this run);
    3. Push an encrypted sclerotium via CnbClient.push (a real git push:
       username cnb, the token as the password) and verify the file reads
       back through the contents API;
    4. Build the spore link (api.cnb.cool raw host) and pull it back with
       Hypha + a Bearer session (the CNB raw endpoint requires the token
       even for public repositories);
    5. Push an update and verify the picker sees the new content;
    6. Cleanup: delete_repo() is attempted — CNB usually refuses OpenAPI
       deletion inside root organizations (HTTP 412), so the repository may
       have to be removed on the CNB web UI afterwards.
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import requests

# tests/interface/ -> project root is three levels up.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mycelium import crypto  # noqa: E402
from mycelium.interface.picker import Hypha  # noqa: E402
from mycelium.interface.sower import CnbClient  # noqa: E402
from mycelium.protocol import Sclerotium  # noqa: E402

TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""
if not TOKEN:
    # Fall back to the development-period test token (tests/interface/tokens.py).
    try:
        from tests.interface.tokens import CNB_TOKEN as TOKEN
    except ImportError:
        pass
if not TOKEN:
    sys.exit("usage: python tests/interface/live_cnb.py <access_token>")

# The probe organization (exists; CNB limits root-org creation per year).
GROUP = "mycelium-cnb-probe"
REPO = f"mycelium-live-{random.randint(10000, 99999)}"
BRANCH = "main"
created_this_run = False


class _TokenSession(requests.Session):
    """Attach the Bearer token to every GET (the raw endpoint requires it)."""

    def __init__(self, token: str):
        super().__init__()
        self._token = token

    def get(self, url, **kwargs):  # noqa: ANN001 - requests get(**kwargs)
        headers = dict(kwargs.pop("headers", None) or {})
        headers["Authorization"] = f"Bearer {self._token}"
        return super().get(url, headers=headers, **kwargs)


def cleanup(client: CnbClient) -> None:
    global created_this_run
    if not created_this_run:
        print(f"  [cleanup] {GROUP}/{REPO} was not created this run - nothing to delete")
        return
    try:
        client.delete_repo()
        print(f"  [cleanup] deleted {GROUP}/{REPO} via OpenAPI")
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        print(
            f"  [cleanup] delete {GROUP}/{REPO} -> HTTP {code} "
            "(CNB blocks OpenAPI deletion in root organizations; "
            "remove it on the CNB web UI if desired)"
        )


def main() -> None:
    global created_this_run
    client = CnbClient(
        TOKEN,
        repo=REPO,
        group=GROUP,
        branch=BRANCH,
        visibility="private",
        poll_interval=1.0,
        max_poll=30,
    )
    # The namespace is the organization path; the profile call validates the
    # token early (GET /user).
    ns = client.namespace
    print(f"[1] token OK, namespace = {ns} (organization path)")

    # [1b] group is optional: without it the organization resolves to the
    # profile username (no creation here — root-org creation is quota-limited
    # and covered by unit tests; an existing empty organization would be
    # reused instead).
    client_default = CnbClient(TOKEN, repo=REPO, branch=BRANCH, visibility="private")
    ns_default = client_default.namespace
    assert ns_default and "/" not in ns_default, f"bad resolved group: {ns_default!r}"
    assert client_default.group == ns_default
    print(f"[1b] group omitted -> organization resolves to {ns_default!r} (profile username)")

    assert client.ensure_repo_exists() is True
    created_this_run = True
    info = client._request("GET", f"/{client._repo_path()}").json()
    assert info["name"] == REPO, f"name mismatch: {info.get('name')!r}"
    assert info["path"] == f"{GROUP}/{REPO}", f"path mismatch: {info.get('path')!r}"
    print(f"[2] created {GROUP}/{REPO} (visibility {info.get('visibility_level')})")

    # Publisher pushes an encrypted sclerotium (a real git push).
    cfg = crypto.new()
    sclerotium = Sclerotium.new("Live Smoke")
    sclerotium.entry("hello v1")
    result = client.push("feed.dat", sclerotium.encrypt(cfg), commit_message="publish v1")
    sha1 = result["commit"]["sha"]
    print(f"[3] pushed encrypted sclerotium (commit {sha1[:12]})")

    # The round-trip is verified through the *subscriber* interface: the
    # spore link points at the api.cnb.cool raw endpoint, which requires the
    # token even for public repositories -> an authenticated Hypha session.
    link = client.spore_link("feed.dat", cfg.vk)
    fetched = Hypha(session=_TokenSession(TOKEN)).pull(link)
    assert fetched.content == sclerotium.content, "content mismatch"
    assert len(fetched) == len(sclerotium), "fruit count mismatch"
    print("[4] pulled + verified via Hypha.pull (subscriber interface)")

    # Default branch check.
    head = client._request("GET", f"/{client._repo_path()}/-/git/head").json()
    assert head["name"] == BRANCH, f"default branch mismatch: {head!r}"
    print(f"[5] default branch confirmed: {head['name']}")

    # Update push: a second commit must be readable as the new content.
    sclerotium.entry("hello v2")
    result = client.push("feed.dat", sclerotium.encrypt(cfg), commit_message="publish v2")
    assert result["commit"]["sha"] != sha1, "update must create a new commit"
    fetched2 = Hypha(session=_TokenSession(TOKEN)).pull(link)
    assert fetched2.content == sclerotium.content, "updated content mismatch"
    assert len(fetched2) == 2, "fruit count after update mismatch"
    print(f"[6] update push verified (commit {result['commit']['sha'][:12]})")

    print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        time.sleep(1)  # let the API settle before cleanup
        cleanup(CnbClient(TOKEN, repo=REPO, group=GROUP, branch=BRANCH))
