"""
Changelog publisher example: maintain a "Change Log" feed (sclerotium) locally.

Usage:
    1. Append new ``(version, entry)`` tuples to the ``entries`` list below,
       in order — versions are semantic (major.minor.patch);
    2. Run:  python examples/eg_changelog.py
    3. The encrypted sclerotium is written to ``ChangeLog.dat`` in this folder
       (the publisher identity is kept in ``config.key``). Commit
       ``ChangeLog.dat`` — it is tracked on purpose (see .gitignore) — so
       the example link stays live.

The feed's mycelium link — ``ChangeLog.dat`` lives at
``examples/ChangeLog.dat`` in this repository (demoliisher/Mycelium on
GitHub) — hardcoded here in comment form:

    # mycelium://8pFEkFBqrQWgw6IzVDA5Lu4fxHvoGGUG69vzvLNoFS7rXjXDwPnqqYhvNs25PNcAexQPwwzK1DEByGpqtRpmmDIBqbvcx9uoWx9M9zqkiN8rRSSmnZ2BHEozf2enAagKTNG=

This script doubles as a usage example of ``mycelium.crypto`` and
``mycelium.protocol``.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mycelium import crypto
from mycelium.protocol import Sclerotium, Spore

# Changelog entries, in order: (semantic version, entry text). Append new
# ones here; entries already present are skipped on subsequent runs.
entries = [
    (
        "0.4.0",
        "CNB module: the commit identity now comes from the platform API "
        "(profile username + git commit email via the account-email:r scope, "
        "profile email as fallback — the git_author parameter and the "
        "neutral fallback identity are gone); restructure the module docs "
        "into per-module files with README package overviews (crypto: "
        "Hash/AES/EdDSA, protocol: core/spore, sower: one document per "
        "platform)",
    ),
    (
        "0.3.0",
        "Add the skills/ directory — task-oriented agent workflows "
        "(release, gate, docs-sync, feed-ops, platform-add) that reference "
        "AGENTS.md instead of restating it",
    ),
    (
        "0.2.4",
        "Link the official CNB references from the sower docs and AGENTS.md "
        "(OpenAPI spec, cnb-skill repository, platform docs)",
    ),
    (
        "0.2.3",
        "Record the official CNB OpenAPI constraints: root_group_protection "
        "is read-only (web-only), sub-organizations are read-only (the "
        "yearly root-org quota cannot be bypassed), git writes exist only "
        "via blobs (a real git push is the only write path), and the "
        "x-cnb-identity-ticket header gates deletes",
    ),
    (
        "0.2.2",
        "CNB module: delete_repo explains the web-only setting 允许通过 "
        "Open API 删除组织下资源 (组织设置 → 管控 → 组织管控 → 危险操作) when "
        "OpenAPI deletion is refused (HTTP 412); docs cover the deletion "
        "rules (empty org required, yearly creation quota not freed by "
        "deletion)",
    ),
    (
        "0.2.1",
        "CNB module: the organization is now optional — when group is "
        "omitted it resolves from the profile username (the username-named "
        "org when it exists, else an existing empty org is reused, else a "
        "username-named org is auto-created)",
    ),
    (
        "0.2.0",
        "Add the CNB (cnb.cool) platform module: organization-based "
        "repositories (auto-created when missing), git-push writes (the "
        "platform has no contents API), and a documented refusal of fork "
        "mode (no fork API on CNB)",
    ),
    (
        "0.1.0",
        "Add the one-command pre-submit gate (scripts/gate.py, check and "
        "auto-fix); move mdtables.py out of the package into scripts/; fold "
        "table alignment into the markdown lint task",
    ),
    (
        "0.0.1",
        "Initial release — encrypted-feed distribution protocol with deterministic "
        "crypto, protobuf wire format and spore links; sower/picker role split "
        "across Gitee, GitCode and GitHub; mycelium ecosystem naming",
    ),
]

# Deployment location of ChangeLog.dat (used only to build the link): the
# file is committed at examples/ChangeLog.dat in this repository on GitHub.
_LINK_HOST = "github.com"
_LINK_PATH = "demoliisher/Mycelium/raw/main/examples/ChangeLog.dat"

_HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    # 1. Load or create the publisher identity, stored as a PKCS#8 PEM key
    #    file (``config.key``); the optional MYCELIUM_KEY_PASSPHRASE env var
    #    encrypts it at rest, and a legacy raw-byte ``config.dat`` is
    #    auto-migrated to PEM on first run.
    config_path = os.path.join(_HERE, "config.key")
    legacy_path = os.path.join(_HERE, "config.dat")
    passphrase = os.environ.get("MYCELIUM_KEY_PASSPHRASE")
    try:
        cfg = crypto.load(config_path, passphrase)
        print("[1] loaded config")
    except FileNotFoundError:
        if os.path.exists(legacy_path):
            cfg = crypto.load(legacy_path)  # legacy raw-byte auto-detected
            crypto.save(config_path, cfg, passphrase)
            print("[1] migrated legacy config.dat -> config.key")
        else:
            cfg = crypto.new()
            crypto.save(config_path, cfg, passphrase)
            print("[1] created config")

    # 2. Load or initialize the changelog sclerotium.
    data_path = os.path.join(_HERE, "ChangeLog.dat")
    try:
        with open(data_path, "rb") as f:
            sclerotium = Sclerotium.decrypt(f.read(), cfg.vk)
        print(f"[2] loaded existing changelog ({len(sclerotium)} fruit(s))")
    except FileNotFoundError:
        sclerotium = Sclerotium.new("Change Log")
        print("[2] created new changelog")

    # 3. Append the entries that are not present yet, in order. Each fruit's
    #    content joins the version and the entry text with a colon.
    stored = {fruit.content for fruit in sclerotium.fruits}
    added = 0
    for version, entry in entries:
        content = f"{version}: {entry}"
        if content not in stored:
            sclerotium.entry(content)
            stored.add(content)
            added += 1
    print(f"[3] added {added} new entry/entries")

    # 4. Encrypt and write the sclerotium data locally.
    binary = sclerotium.encrypt(cfg)
    with open(data_path, "wb") as f:
        f.write(binary)
    print(
        f"[4] wrote {data_path} ({len(binary)} bytes, edition {sclerotium.edition})"
    )

    # 5. The sclerotium's spore link (hardcoded in the docstring above).
    link = Spore(_LINK_HOST, _LINK_PATH, cfg.vk).export()
    print("[5] spore link (commit ChangeLog.dat to this repository to make it live):")
    print("    " + link)


if __name__ == "__main__":
    main()
