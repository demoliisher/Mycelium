# Skills

Task-oriented workflow skills for AI agents (and humans) working in this
repository. Think of them as the **how** next to `AGENTS.md`'s **what**:
`AGENTS.md` states the rules (non-negotiables, conventions, platform
quirks); each skill below is a step-by-step procedure for a recurring
job, referencing the rules instead of restating them.

`SKILL.md` uses the common format (YAML frontmatter with `name` and
`description`, then markdown instructions), so any skills-aware agent —
Claude Code, CodeBuddy, `npx skills`, or a custom harness — can load a
directory directly.

## Available skills

| Skill                                   | Purpose                                                                                                                        |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| [`release`](release/SKILL.md)           | Full release workflow: version bump, changelog triple-sync, gate, identity audit, mandatory user approval, commit + tag + push |
| [`gate`](gate/SKILL.md)                 | Pre-submit gate: run check-and-fix, handle failures, identity audit                                                            |
| [`docs-sync`](docs-sync/SKILL.md)       | Documentation sync: EN source of truth, zh-Hans mirror, tables, changelog, classical-Chinese no-go zone                        |
| [`feed-ops`](feed-ops/SKILL.md)         | Feed operations: publish/subscribe examples, PEM keys, spore-link verification rules                                           |
| [`platform-add`](platform-add/SKILL.md) | Add a storage backend: git-hosting platform (`GitPlatformClient`) or non-git service (`Storage`)                               |

## Guidelines

- Skills are **workflows, not rules** — always read `AGENTS.md` and the
  module docs before executing.
- Keep each skill focused; add a new one only when a recurring job has
  enough steps to be worth encoding.
- The frontmatter `name` and the `#` heading must **match the folder
  name** exactly (no `mycelium-` prefix) — skill loaders and editors
  warn when they diverge.
- Markdown in this directory is linted by the gate — run
  `uv run python scripts/gate.py` after editing.
