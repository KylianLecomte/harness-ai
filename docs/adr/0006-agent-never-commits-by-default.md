# ADR-0006 — The agent never commits by default

- **Status:** accepted
- **Date:** 2026-09-30

## Context

The user must stay in control of the project history. Autonomy is a user choice, not a default.

## Decision

`workflow.agent_commits` defaults to `false` in every preset. When false, a Claude Code hook
(`block_git_commit`) refuses `git commit` and `git push`, and `AGENTS.md` states the rule for
agents without hooks. The agent proposes a commit message; the user commits. The same rule applies
while developing HarnessAI itself.

## Consequences

- The user can opt in per project by setting `agent_commits = true`.
- Skills end with "changes ready for review" rather than a commit.
