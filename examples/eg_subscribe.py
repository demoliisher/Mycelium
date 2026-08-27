"""
Subscriber demo: parse a spore link, download, decrypt, verify and preview.

Pipeline:
    1. Take a ``mycelium://`` spore link (argv, MYCELIUM_LINK env, or an
       interactive prompt);
    2. The hypha parses host/path/vk from the link and downloads the feed;
    3. The feed is decrypted and signature-verified;
    4. A human-readable preview is printed.

Public spores download anonymously — only the verification key is needed.
For a private spore, answer "y" when asked and provide an access token.

Run:
    python examples/eg_subscribe.py                    # prompts for the link
    python examples/eg_subscribe.py "mycelium://..."   # or pass it directly
    $env:MYCELIUM_LINK='mycelium://...'; python examples/eg_subscribe.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from mycelium.interface.picker import Hypha
from mycelium.protocol.core import preview


def _get_link() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    env = os.environ.get("MYCELIUM_LINK")
    if env:
        return env
    link = input("mycelium:// spore link: ").strip()
    if not link:
        raise SystemExit("no spore link given")
    return link


def main() -> None:
    link = _get_link()

    # Public spores download anonymously; for a private spore the download
    # needs an access token attached to the request (e.g. Gitee's API raw
    # endpoint reads it as a query parameter).
    hypha = Hypha()
    if input("Require an access token (private spore)? [y/N] ").strip().lower() in (
        "y",
        "yes",
    ):
        token = input("Access token: ").strip()
        if token:
            session = requests.Session()
            session.params = {"access_token": token}
            hypha = Hypha(session=session)

    sclerotium = hypha.pull(link)
    print(
        f"verified sclerotium: {sclerotium.content!r} "
        f"(edition {sclerotium.edition}, {len(sclerotium)} fruit(s))"
    )
    preview(sclerotium)


if __name__ == "__main__":
    main()
