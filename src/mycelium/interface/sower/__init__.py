# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Sower interface: push the encrypted feed blob into a hosting backend.

``base`` holds the abstract contracts: ``Storage`` (push-only, shared by
all platforms) and ``GitPlatformClient`` (the git-hosting lifecycle as a
pure abstract contract — every method is a ``pass`` placeholder, ``push``
stays abstract from ``Storage``). Each platform gets its own self-contained
module implementing the full lifecycle (``gitee``, ``gitcode``, ``github``
— other hosts can be added later as siblings, e.g. a plain WebDAV server
subclassing ``Storage``).
"""

from .base import GitPlatformClient, Storage
from .gitee import GiteeClient
from .gitcode import GitCodeClient
from .github import GithubClient

__all__ = [
    "Storage",
    "GitPlatformClient",
    "GiteeClient",
    "GitCodeClient",
    "GithubClient",
]
