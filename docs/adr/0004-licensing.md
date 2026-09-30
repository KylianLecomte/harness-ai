# ADR-0004 — MIT for the harness, MIT-0 for the template

- **Status:** accepted
- **Date:** 2026-09-30

## Context

HarnessAI is open source. Files under `template/` are copied into users' projects: a copyleft
licence (GPL) would force those projects under the same licence, and even MIT would oblige users
to carry the harness copyright notice in every generated project.

## Decision

- The harness (skills, scripts, catalog, docs) is licensed under **MIT**.
- `template/` is licensed under **MIT-0** (no attribution required): generated files fully belong
  to the user.

## Consequences

- Maximum adoption; commercial use allowed.
- Contributors must be told that contributions under `template/` are MIT-0.
