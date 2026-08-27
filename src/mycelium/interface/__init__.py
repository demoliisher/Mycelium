# Copyright (c) 2026 demoliisher
# SPDX-License-Identifier: MIT
"""
Role-based interface layer: the sower and the picker.

- ``sower`` — push the encrypted feed blob into a hosting backend
  (``Storage`` contract; ``GitPlatformClient`` in ``sower/base.py`` is
  the abstract git-hosting contract — a pure abstract class, every method a
  ``pass`` placeholder and ``push`` inherited abstract from ``Storage``;
  each platform module under ``sower/`` implements the full lifecycle
  itself, e.g. ``gitee`` → ``GiteeClient``, ``gitcode`` → ``GitCodeClient``);
- ``picker`` — pull a spore link and turn it into a verified plaintext
  channel (``Hypha``).
"""

from .sower import GiteeClient, GitCodeClient, GithubClient, GitPlatformClient, Storage
from .picker import Hypha

__all__ = [
    "Storage",
    "GitPlatformClient",
    "GiteeClient",
    "GitCodeClient",
    "GithubClient",
    "Hypha",
]
