# HarnessAI — Plan

> Reference plan for building HarnessAI. It records every decision taken during the initial
> framing (2026-09-30). Load-bearing decisions also have an ADR in [`adr/`](adr/).
> Keep this file up to date when a decision changes — and add or supersede the matching ADR.

## 1. Vision

HarnessAI is an open-source harness to start **any kind of project** in agentic development
(web, mobile, backend, IoT, CLI, data…) with **the right level of quality**, and to carry it
through its whole lifecycle with an AI agent: frame, plan, build, test, review, deploy.

```
/new-project <name>
```

The agent interviews the user, adapts the depth of the interview to the chosen quality level,
completes and challenges the technical choices, lets the user validate a single project contract
(`harness.toml`), then generates a repository where any agent has everything it needs to produce
the best possible code for that project.

## 2. Principles

1. **One contract per project: `harness.toml`.** Project skills hard-code nothing: they read
   the contract (e.g. `/implement` does TDD only if `workflow.methodology = "tdd"`). → ADR-0001
2. **Presets are defaults, not cages.** A preset fills the contract; the user edits it freely.
3. **Scripts for the mechanical, AI for the content.** File copying and templating are done by a
   deterministic script; framing, stack choices and writing docs are done by the AI. → ADR-0003
4. **Agent-agnostic.** `AGENTS.md` is the source of truth; skills follow the open `SKILL.md`
   format. Claude Code–specific features (hooks, permissions, `AskUserQuestion`) are bonuses that
   degrade gracefully. → ADR-0002
5. **The agent never commits by default** (`workflow.agent_commits = false`), enforced by a hook
   where the agent supports it. → ADR-0006
6. **Nothing invented.** Anything not said or validated goes to *Open questions*. Tool and library
   versions are checked online, never written from memory.
7. **Propose rather than ask.** Every question comes with a recommendation derived from what is
   already known. The user corrects a draft faster than they fill a blank page.
8. **A standard without verification does not exist.** Every quality requirement states its
   threshold *and* how it is checked (tool, CI step, review checklist item).
9. **Language:** the harness itself (skills, docs, catalog) is written in English. The interview
   and the generated project docs use the languages chosen by the user.

## 3. Repository layout

```
harness-ia/
├── README.md, LICENSE (MIT), AGENTS.md, CLAUDE.md
├── docs/
│   ├── PLAN.md                    # this file
│   └── adr/                       # decisions about the harness itself
├── skills/                        # GLOBAL skills, installed on the user's machine
│   ├── new-project/               # folder → interview → contract → generation
│   └── harness-sync/              # bring template updates into an existing project
├── catalog/
│   ├── harness.schema.json        # THE definition of harness.toml (source of truth)
│   ├── presets/                   # prototype | poc | mvp | small | large .toml
│   ├── interview/                 # one file per interview theme
│   ├── stack/                     # universal stack dimensions (+ profiles, later)
│   └── standards/                 # reference standards mapped to presets
├── template/                      # copied into each project (LICENSE: MIT-0)
│   ├── AGENTS.md.tmpl, CLAUDE.md.tmpl
│   ├── docs/                      # SPEC, CONTEXT, ARCHITECTURE, STACK, QUALITY, adr/, …
│   ├── skills/                    # project lifecycle skills (§8)
│   ├── adapters/                  # claude/ (settings, hooks), cursor/, copilot/, …
│   └── infra/                     # mise.toml, ci/, docker/, devcontainer/ (conditional)
├── scripts/                       # harness.py: scaffold, check, doc generation
└── examples/                      # reference generated projects = regression tests
```

Template conventions (to be detailed in phase 2): files the tooling would otherwise pick up are
stored under inert names (`dot_claude/` → `.claude/`, `AGENTS.md.tmpl` → `AGENTS.md`), so that
working on the harness never loads a template as live configuration.

## 4. The project contract: `harness.toml`

### Three layers

| Layer | Content | Read by |
|---|---|---|
| `harness.toml` | the **knobs**: stack pillars, commands, quality thresholds, workflow | skills, scripts |
| `docs/STACK.md`, `docs/QUALITY.md` | the **justified detail** | the AI and humans |
| Tool configs (lint, CI, `mise.toml`, hooks…) | the **enforcement** | tools |

### Definition and reference

`catalog/harness.schema.json` is the single source of truth: for every key it gives the
description, allowed values, default per preset and effect. `scripts/harness.py doc` **generates**
the human-readable reference (`docs/harness-toml.md`) from it, so the two can never drift.
Every generated project links to that reference.

### Short example

```toml
[project]
name = "budgeto"
preset = "mvp"                # prototype | poc | mvp | small | large
language = { docs = "fr", code = "en", commits = "en" }

[stack]                       # user-imposed, completed by the AI (justified in ADR-0001 of the project)
frontend = "react"            # imposed
backend  = "java-spring"      # imposed
database = "postgresql"       # proposed
mobile   = "react-native"     # proposed

[commands]                    # skills and CI run exactly these
test = "mise run test"
lint = "mise run lint"

[workflow]
methodology = "spec-driven"   # none | spec-driven | tdd
agent_commits = false
plan_before_code = true

[tests]
unit = true
integration = true
e2e = false
coverage_min = 70

[security]
asvs_level = 1
dependency_audit = true
secrets_scan = true

[performance]
web_vitals = "measured"       # off | measured | enforced
api_p95_ms = 300

[accessibility]
wcag = "AA"

[compliance]
gdpr = true
health_data = false

[docs]
adr = true
context_glossary = true

[ops]
ci = "github-actions"
docker = true
devcontainer = false

[agent.hooks]
format_on_edit = true
self_review = true            # re-read own diff against the contract before handing back
verify_on_stop = false
block_git_commit = true       # derived from workflow.agent_commits = false
```

The full catalog will hold around fifty indicators (phase 1).

## 5. Quality presets and standards

| Preset | Purpose |
|---|---|
| `prototype` | show an idea or a UX to someone; may be thrown away |
| `poc` | prove a technical feasibility (one risky question); thrown away |
| `mvp` | first usable version for real users |
| `small` | a project meant to last, limited scope |
| `large` | production, many features, long-lived, possibly a team |

Standards come from recognised references rather than invented rules (`catalog/standards/`):

| Domain | Reference | poc | mvp | small | large |
|---|---|---|---|---|---|
| Web security | OWASP ASVS (levels 1–3) | — | L1 | L1 | L2 |
| Mobile security | OWASP MASVS | — | L1 | L1 | L2 |
| Web performance | Core Web Vitals (LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1) | — | measured | measured | enforced in CI |
| API performance | p95 latency target | — | indicative | target | enforced |
| Accessibility | WCAG 2.2 | — | A | AA | AA |
| Code | coverage / complexity / duplication | — | 60 % | 70 % | 80 % |
| Personal data | GDPR (+ art. 9 / HDS for health data) | — | per data | per data | per data |

`prototype` follows `poc` except where it has a UI worth caring about (light accessibility).
Domain-specific standards (e.g. ETSI EN 303 645 / Cyber Resilience Act for IoT) are identified by
the AI during the interview, like domain stack dimensions (§6).

`docs/QUALITY.md` lists each requirement with its threshold and its verification.

## 6. Stack model → ADR-0005

- **Universal dimensions** (`catalog/stack/dimensions.md`): languages, runtime and toolchain
  (versions pinned with mise), dependencies, build, lint/format, tests, CI/CD, secrets,
  observability, distribution/deployment.
- **Domain dimensions are derived by the AI** from what the user describes (web routing and data
  fetching, mobile build and distribution, IoT firmware/RTOS/protocols/OTA, …), then submitted to
  the user for validation. No closed list of project families: nothing is ever unsupported.
- **Later: profiles** (`catalog/stack/profiles/web.md`, `iot.md`, …): an open, community-contributed
  set of default framings that *speed up* the interview but never gate it.
- Each choice in `docs/STACK.md` states: version (checked), **imposed or proposed**, why,
  rejected alternatives, and phase (from the start / deferred). The user may impose part of the
  stack (e.g. React + Java); the AI completes the rest and flags imposed choices that fit poorly.
- Tooling install plan: the AI generates `mise.toml` and runs `mise install` with the user's
  confirmation (or leaves it to the user) — skill `/setup-env`.

## 7. The adaptive interview

### Themes per preset

● full · ◐ light · — skipped

| # | Theme | prototype | poc | mvp | small | large |
|---|---|---|---|---|---|---|
| 1 | Vision and problem | ● | ● | ● | ● | ● |
| 2 | Users and key journeys | ◐ | — | ● | ● | ● |
| 3 | Scope: MoSCoW, non-goals (poc: hypothesis + success criterion) | ◐ | ● | ● | ● | ● |
| 4 | Platforms and project type | ● | ● | ● | ● | ● |
| 5 | Domain and glossary | — | — | ◐ | ● | ● |
| 6 | Stack (§6) | ◐ | ◐ | ● | ● | ● |
| 7 | Architecture | — | ◐ | ◐ | ● | ● |
| 8 | Data and compliance | — | — | ● | ● | ● |
| 9 | Auth and authorisation | — | — | ● | ● | ● |
| 10 | Security | — | — | ◐ | ● | ● |
| 11 | Performance | — | — | ◐ | ● | ● |
| 12 | Errors and observability | — | — | ◐ | ● | ● |
| 13 | Accessibility and i18n | ◐ | — | ◐ | ● | ● |
| 14 | Deployment and environments | — | — | ● | ● | ● |
| 15 | Way of working (method, git, languages, autonomy) | ◐ | ◐ | ● | ● | ● |

Indicative volume: poc ≈ 6 questions in 2 rounds · mvp ≈ 15–25 in 4–5 rounds · large ≈ 40+.
These are defaults, adjustable in the catalog.

### One file per theme — `catalog/interview/<theme>.md`

```markdown
---
id: security
presets: { mvp: light, small: full, large: full }
when: has_users or stores_data        # otherwise skipped
outputs: [docs/QUALITY.md#security, harness.toml#security]
---
## Goal                  what this theme must establish
## Reference questions   examples to adapt to the project, not a script
## Defaults per preset   what the AI proposes when the user has no opinion
## Challenge signals     e.g. "health data in a poc", "home-made auth in production"
## Done when             the output sections can be written without inventing anything
```

### Common rules (in the `new-project` SKILL.md)

- Rounds of 3–4 questions max, each with a recommended answer.
- What can be inferred from the pitch is not asked again; it is marked *inferred* in the summary.
- "Up to you" → default, recorded as an assumption. "Skip" → *Open questions*.
- Challenge from each theme's signals, plus a global rule: scope too large for the preset is
  always flagged.

### Flow of `/new-project <name>`

1. Free-text pitch (idea, desired stack even partial, constraints).
2. Preset choice — the AI recommends one; it sets the interview depth.
3. Adaptive interview (themes above).
4. Stack completion and version checks.
5. **Validation:** the AI writes `harness.draft.toml` (complete, commented) and shows the framing
   summary. The user opens it, edits it, validates. The AI re-reads the edits and challenges them
   if needed. **Nothing is generated before this validation.**
6. Generation: `scripts/harness.py` scaffolds, then the AI fills the docs.
7. Optional steps, each proposed separately: `git init`, GitHub repo, `mise install`, stack
   scaffolding (`create-vite`, Spring Initializr, …), roadmap, GitHub issues.
8. Hand-off: what was created and the next command (`/plan`).

### Framing outputs

`AGENTS.md` (+ `CLAUDE.md` importing it), `docs/SPEC.md`, `docs/CONTEXT.md` (domain glossary),
`docs/ARCHITECTURE.md`, `docs/STACK.md`, `docs/QUALITY.md`, `docs/adr/0001-stack.md`, and optional
`docs/ROADMAP.md` — each only when the preset calls for it.

## 8. Skills

**Global** (installed once): `/new-project <name>`, `/harness-sync`.

**Project** (copied into each project, some only depending on the contract):

| Phase | Skill | Role |
|---|---|---|
| Plan | `/plan` | roadmap and task breakdown; GitHub issues optional |
| Build | `/implement <task>` | follows `workflow` and `tests` (TDD, plan validated first, …) |
| Verify | `/verify` | runs the quality gate (`[commands]`) and gives a verdict |
| Review | `/review` | reviews against the contract, `CONTEXT.md` and the ADRs |
| Decide | `/adr` | records a decision |
| Architecture | `/improve-architecture` | portable take on deep modules / seams (small and large) |
| Deploy | `/deploy` | prepares or runs deployment to the chosen target |
| Evolve | `/upgrade-quality [preset]` | §9 |
| Tooling | `/setup-env` | generates `mise.toml`, runs `mise install` after confirmation |

Architecture concepts adopted in the templates (from *A Philosophy of Software Design* and
*Working Effectively with Legacy Code*): deep modules, the deletion test, seams, "the interface
is the test surface", a domain glossary (`CONTEXT.md`) and ADRs so the agent does not re-litigate
decisions.

## 9. Upgrading and syncing

- `.harness/lock.toml` stores the contract as last applied, plus the template version used.
- `/upgrade-quality` with no argument diffs `harness.toml` against the lock: manual edits are
  detected automatically and the delta is applied (CI, hooks, missing docs, skills to enable).
- `/upgrade-quality <preset>` first merges the new preset while keeping manual overrides.
- In both cases it **challenges** changes against the rest of the contract and the ADRs
  ("you disabled integration tests while storing health data — I suggest…"); the user decides.
- `/harness-sync` compares the project's template version with the latest and proposes updates
  file by file, never overwriting customised content.

## 10. Agent compatibility and hooks → ADR-0002, ADR-0006

- `AGENTS.md` is canonical; `CLAUDE.md` contains `@AGENTS.md` plus Claude-specific notes.
- Project skills live in `.agents/skills/`, symlinked into `.claude/skills/` and other agents'
  locations.
- Global install: `npx skills add <repo>` (targets several agents), with `install.sh` as fallback.
- Claude Code hooks, driven by `[agent.hooks]`:

| Hook | Trigger | Default |
|---|---|---|
| `format_on_edit` | after each file edit → run the formatter | mvp+ |
| `self_review` | end of a turn that modified files → re-read the diff against `CONTEXT.md`, ADRs and `QUALITY.md`, once (loop guard) | mvp+ |
| `verify_on_stop` | end of a turn → lint + tests, send the agent back on failure | small+ |
| `block_git_commit` | before a shell command → refuse `git commit` / `git push` | whenever `agent_commits = false` |

  For agents without hooks, the same rules are written in `AGENTS.md` (weaker, still useful).

## 11. Roadmap

| # | Phase | Verifiable outcome |
|---|---|---|
| 0 | Repo init, licences, this plan, harness ADRs | clean skeleton ✅ |
| 1 | Indicator catalog, `harness.schema.json`, 5 presets, generated reference | `harness.py check` validates every preset |
| 2 | Doc templates, `AGENTS.md`, scaffold script | dry-run generation of one project per preset |
| 3 | `/new-project` — first poc, then all presets | nutrition app poc framed end to end |
| 4 | `/plan`, `/implement`, `/verify`, `/review`, `/adr` | a real feature shipped in the budget app (mvp) |
| 5 | `/upgrade-quality` + lock | nutrition app upgraded poc → mvp without breakage |
| 6 | `/setup-env` (mise), `/deploy`, Docker/devcontainer, GitHub issues | budget mvp deployed |
| 7 | Cursor/Copilot adapters, `/harness-sync`, `/improve-architecture` | same project driven from another agent |
| 8 | README, examples, harness CI, publication | open-source release |

Test projects: a **nutrition app** (Yazio-like, poc, phases 3 and 5) and a **budget app**
(YNAB-like, web + mobile, mvp, phases 4 and 6).

## 12. Later / open

- Stack profiles by project type (§6).
- Profiles for standards by domain.
- Interview themes contributed by the community.
