# ADR-0005 — Open stack model: universal dimensions + AI-derived domain dimensions

- **Status:** accepted
- **Date:** 2026-09-30

## Context

HarnessAI must support any kind of project. An IoT project shares almost nothing with a web app.
A closed list of project families would inevitably leave some projects unsupported, and a catalog
of libraries would be outdated within months.

## Decision

- The catalog lists **universal stack dimensions** (languages, toolchain, dependencies, build,
  lint/format, tests, CI/CD, secrets, observability, distribution).
- **Domain dimensions and domain standards are derived by the AI** from the user's description,
  then submitted for validation. The catalog holds questions to settle, not libraries.
- Versions are always checked online at framing time.
- Stack **profiles** by project type may come later as open, community-contributed accelerators;
  they never gate the interview.

## Consequences

- Quality of domain framing relies on the model; the validation step (`harness.draft.toml`) is
  the safety net.
- `docs/STACK.md` must always state, per choice: version, imposed/proposed, rationale, rejected
  alternatives, phase.
