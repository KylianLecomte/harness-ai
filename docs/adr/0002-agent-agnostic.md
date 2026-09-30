# ADR-0002 — Agent-agnostic by design

- **Status:** accepted
- **Date:** 2026-09-30

## Context

The author uses Claude Code today, but HarnessAI is open source and must work with other agents
(Cursor, Codex, Copilot, Gemini CLI, …). Each agent reads its own instruction files and skill
locations.

## Decision

- `AGENTS.md` is the canonical instruction file; `CLAUDE.md` imports it (`@AGENTS.md`) and only
  adds Claude-specific notes.
- Skills follow the open `SKILL.md` format and live in `.agents/skills/`, symlinked into each
  agent's location.
- Agent-specific features (Claude Code hooks, permissions, `AskUserQuestion`) are optional
  adapters under `template/adapters/`. Skills must degrade gracefully without them (e.g. ask
  questions as plain text when no question tool exists).
- Global install through `npx skills add <repo>`, with `install.sh` as fallback.

## Consequences

- Rules enforced by Claude hooks must also be written in `AGENTS.md` for other agents.
- Each new agent adapter is additive and does not touch the core.
