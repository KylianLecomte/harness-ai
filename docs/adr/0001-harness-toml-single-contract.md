# ADR-0001 — `harness.toml` is the single project contract

- **Status:** accepted
- **Date:** 2026-09-30

## Context

Projects range from a throwaway poc to a long-lived production app. Hard-coding behaviour per
quality level (fixed template layers) makes every level rigid and prevents fine-tuning. Skills,
CI and hooks need one place to read the project's rules from.

## Decision

Every generated project has a `harness.toml` holding the knobs: stack pillars, commands, workflow,
quality thresholds, agent hooks. Presets (`prototype`, `poc`, `mvp`, `small`, `large`) only fill
default values; the user edits the file freely. Project skills read the contract at runtime and
hard-code nothing. Detail lives in docs (`STACK.md`, `QUALITY.md`), enforcement in tool configs.
`catalog/harness.schema.json` defines every key; the human-readable reference is generated from it.

## Consequences

- Upgrading quality becomes a diff between the contract and `.harness/lock.toml`.
- The schema must be maintained carefully: it is the harness's public API.
- Skills must degrade sensibly when a key is absent (use the preset default).
