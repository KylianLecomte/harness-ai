# HarnessAI

> **Status: work in progress** — phase 2 of the [roadmap](docs/PLAN.md#11-roadmap). Nothing is
> installable yet.

Start **any project** in agentic development — web, mobile, backend, IoT, CLI, data… — with the
right level of quality, and drive it through its whole lifecycle with an AI agent.

```
/new-project <name>
```

1. The agent interviews you. The depth adapts to the quality level you pick
   (`prototype`, `poc`, `mvp`, `small`, `large`): a poc takes a few questions, a production
   project gets properly framed.
2. It completes your stack (impose what you want, e.g. React + Java; it proposes the rest and
   challenges what fits poorly) and checks versions online.
3. You validate a single, editable project contract: `harness.toml`.
4. It generates a repository ready for agentic work: `AGENTS.md`, framing docs (spec, domain
   glossary, architecture, stack, quality requirements, ADRs), lifecycle skills (`/plan`,
   `/implement`, `/verify`, `/review`, `/deploy`, `/upgrade-quality`…), agent hooks, CI.

Works with any agent that reads `AGENTS.md` and `SKILL.md` skills; Claude Code gets extras
(hooks, permissions, interactive questions).

## Documentation

- [Plan](docs/PLAN.md) — vision, design and roadmap
- [`harness.toml` reference](docs/harness-toml.md) — every key, its values and its default per preset
- [Architecture decisions](docs/adr/)

## Licence

- HarnessAI: [MIT](LICENSE)
- Files generated into your project (`template/`): [MIT-0](template/LICENSE) — they are yours,
  no attribution required.
