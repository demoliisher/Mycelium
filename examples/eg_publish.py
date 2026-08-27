"""
Publisher demo: encrypt a sclerotium (feed) and publish it to a Gitee repository as a spore.

Pipeline:
    1. Create (or load) a publisher crypto configuration;
    2. Build a sclerotium with several fruits of varying content length;
    3. Encrypt & sign the whole sclerotium -> obfuscated wire bytes;
    4. Ask for the deployment info in the terminal (access token, target
       repository, ...) and push the bytes to that repository;
    5. Build a Spore (host/path/vk) and export it as a ``mycelium://`` link.

Everything the demo needs is entered interactively in the terminal — the
access token and the target repository are user input, never hardcoded,
and no file is generated in any other designated remote repository.
``--local`` additionally writes the encrypted blob to ``feed.dat`` next to
this script.

Run:
    python examples/eg_publish.py [--local]

The printed spore link is all a subscriber needs; pass it to
examples/eg_subscribe.py.

Spore link URLs: with public repositories the spore path is the plain web raw URL
and subscribers download anonymously — only the verification key is needed.
For private repositories the spore path would be the Gitee API raw endpoint
and the subscriber must attach an access token.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mycelium import crypto
from mycelium.interface.sower import GiteeClient
from mycelium.protocol import Sclerotium, Spore, parse as parse_spore

HOST = "gitee.com"
FEED_FILE = "feed.dat"

_HERE = os.path.dirname(os.path.abspath(__file__))


def _push(wire: bytes, target: dict, token: str) -> str:
    """Push ``wire`` to ``target``; return the spore path for the link."""
    client = GiteeClient(token, repo=target["repo"], branch=target["branch"])
    client.ensure_repo_exists()
    client.push(target["path"], wire, commit_message="publish demo feed")
    owner = client.namespace  # personal space (个人空间) resolved from the API
    if target["api"]:
        return f"api/v5/repos/{owner}/{target['repo']}/raw/{target['path']}"
    return f"{owner}/{target['repo']}/raw/{target['branch']}/{target['path']}"


def main() -> None:
    write_local = "--local" in sys.argv[1:]

    # 0. Ask for the deployment info in the terminal. ``api=True`` selects
    #    the Gitee API raw endpoint in the spore path (required for *private*
    #    repositories, where the subscriber must attach an access token);
    #    ``api=False`` uses the plain web raw URL, which public repositories
    #    serve anonymously — only the verification key is needed.
    token = input("Gitee access token: ").strip()
    if not token:
        raise SystemExit("no access token given")
    repo = input("Target repository name (in your account; created when missing): ").strip()
    if not repo:
        raise SystemExit("no repository given")
    branch = input("Branch [master]: ").strip() or "master"
    path = input(f"File path [{FEED_FILE}]: ").strip() or FEED_FILE
    private = input("Private repository (subscriber needs a token)? [y/N] ").strip().lower() in (
        "y",
        "yes",
    )
    target = {"repo": repo, "branch": branch, "path": path, "api": private}

    # 1. Publisher configuration (stable identity, reused across runs),
    #    stored as a PKCS#8 PEM key file (``publisher.key``). The optional
    #    MYCELIUM_KEY_PASSPHRASE env var encrypts the key at rest; a legacy
    #    raw-byte ``publisher.dat`` is auto-migrated to PEM on first run.
    config_path = os.path.join(_HERE, "publisher.key")
    legacy_path = os.path.join(_HERE, "publisher.dat")
    passphrase = os.environ.get("MYCELIUM_KEY_PASSPHRASE")
    try:
        cfg = crypto.load(config_path, passphrase)
        print("[1] loaded publisher config")
    except FileNotFoundError:
        if os.path.exists(legacy_path):
            # crypto.load auto-detects the legacy raw-byte format.
            cfg = crypto.load(legacy_path)
            crypto.save(config_path, cfg, passphrase)
            print("[1] migrated legacy publisher.dat -> publisher.key")
        else:
            cfg = crypto.new()
            crypto.save(config_path, cfg, passphrase)
            print("[1] created publisher config")
    print("    vk:", cfg.vk.hex()[:24], "...")

    # 2. Sclerotium with fruits of varying content length.
    sclerotium = Sclerotium.new("Mycelium Demo Feed")
    sclerotium.entry("Short post.")
    sclerotium.entry(
        "A medium-length post with a few more words to make the ciphertext differ."
    )
    sclerotium.entry(
        "A longer post: "
        + "lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 4
    )
    print(
        f"[2] sclerotium ready: {len(sclerotium)} fruit(s), "
        f"edition {sclerotium.edition}"
    )

    # 3. Encrypt & sign the whole sclerotium -> obfuscated wire bytes.
    wire = sclerotium.encrypt(cfg)
    print(f"[3] encrypted {len(wire)} bytes")

    # 4. Optionally write the blob locally as well.
    if write_local:
        local_path = os.path.join(_HERE, FEED_FILE)
        with open(local_path, "wb") as f:
            f.write(wire)
        print(f"[4] wrote local copy: {local_path}")

    # 5. Push to the user-chosen repository.
    spore_path = _push(wire, target, token)
    print(f"[5] pushed to {repo}")

    # 6. Spore + exported link.
    spore = Spore(HOST, spore_path, cfg.vk)
    link = spore.export()
    print("[6] spore link (pass to eg_subscribe.py or set MYCELIUM_LINK):")
    print("    " + link)

    # Sanity: the link must round-trip to the same spore.
    assert parse_spore(link) == spore
    print("    (link round-trip verified)")


if __name__ == "__main__":
    main()
