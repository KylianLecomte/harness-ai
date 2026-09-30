# ADR-0003 — Scaffold script in dependency-free Python, with AI fallback

- **Status:** accepted
- **Date:** 2026-09-30

## Context

Generating a project (copying templates, replacing variables, keeping only files relevant to the
contract) must be reproducible and testable, and must not require users to install anything
unusual. The script must be easy to read for contributors.

## Decision

`scripts/harness.py` is written in Python 3 using only the standard library (`tomllib` needs
Python ≥ 3.11). It scaffolds, validates contracts (`check`) and generates the `harness.toml`
reference (`doc`). If Python is unavailable, the skill falls back to the AI copying files by
following the template manifest: the script adds reproducibility, it is not a hard requirement.

## Consequences

- Python ≥ 3.11 is present by default on most Linux/WSL setups and recent macOS dev setups.
- No third-party TOML writer: when the script must write TOML, it uses a small dedicated writer.
- The manifest format must be readable by both the script and the AI.
