# HarnessAI — agent instructions

You are working on **HarnessAI itself**: an open-source harness that frames and drives any
project in agentic development. Read [`docs/PLAN.md`](docs/PLAN.md) before any non-trivial change;
decisions are in [`docs/adr/`](docs/adr/) — do not re-litigate them, propose a new ADR instead.

## Rules

- **Never commit or push.** Propose a commit message; the user commits (ADR-0006).
- **English** for everything in this repository (skills, catalog, docs, code, comments).
- **Agent-agnostic** (ADR-0002): no core feature may depend on one agent. Agent-specific
  features go under `template/adapters/` and must degrade gracefully.
- **Scripts:** Python ≥ 3.11, standard library only (ADR-0003).
- **`template/` is inert.** It is copied into users' projects; nothing in it must be picked up as
  live configuration while working on the harness. Use inert names (`dot_claude/`,
  `AGENTS.md.tmpl`). `template/LICENSE` (MIT-0) is not copied into generated projects.
- **`catalog/harness.schema.json` is the public API** of HarnessAI. Any key change updates the
  presets, the generated reference and, if breaking, gets an ADR.
- Keep `docs/PLAN.md` in sync when a decision changes, and tick roadmap phases when done.

## Checks

Run before handing back any change to the catalog or the scripts:

```bash
python3 scripts/harness.py doc                    # regenerate docs/harness-toml.md
python3 scripts/harness.py check                  # schema, presets, manifest, templates, reference
python3 -m unittest discover -s scripts/tests     # script tests
```

## Template syntax

Files under `template/` are listed in `template/manifest.toml` (`src`, optional `dest` and `when`).
`.tmpl` files are rendered against the effective contract plus `harness.version`, `harness.date`
and `harness.throwaway` (true for prototype and poc):

- `{{ tests.coverage_min }}` — a value; a missing key is an error; lists render comma-separated.
- `{% if cond %}` / `{% elif cond %}` / `{% else %}` / `{% endif %}` — **alone on their line**
  (the line is removed). No loops.
- Conditions: dotted keys (missing → false), `"strings"`, numbers, `true`/`false`,
  `== != >= <= > <`, `in`, `not`, `and`, `or`, parentheses. Enums are strings: write
  `tests.e2e != "off"`, not `tests.e2e`.
- `<!-- FILL: instruction -->` (or `# FILL:` / `// FILL:` outside Markdown) marks content the AI
  writes from the interview; `harness.py fills <dir>` lists what is left.

`harness.py check` renders every template for every preset, so syntax errors and unknown keys are
caught before they reach a user.

## Layout

| Path | Content |
|---|---|
| `skills/` | global skills installed on the user's machine (`new-project`, `harness-sync`) |
| `catalog/` | schema, presets, interview themes, stack dimensions, standards |
| `template/` | files copied into each generated project (MIT-0) |
| `scripts/` | `harness.py` — scaffold, check, doc generation |
| `examples/` | reference generated projects, used as regression tests |
| `docs/` | plan and ADRs of the harness |
