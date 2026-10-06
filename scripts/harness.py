#!/usr/bin/env python3
"""HarnessAI command-line tool (Python >= 3.11, standard library only — see ADR-0003).

Usage:
  harness.py check [CONTRACT ...]           validate the catalog (no argument) or project contracts
  harness.py resolve CONTRACT               print the effective contract (preset + overrides + derived) as JSON
  harness.py doc [--check]                  generate docs/harness-toml.md; --check fails if it is outdated
  harness.py new CONTRACT --dest DIR [--dry-run]
                                            generate a project from a validated contract
  harness.py fills DIR                      list the FILL markers left in a generated project
"""
from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    sys.exit("harness.py needs Python >= 3.11 (for tomllib).")

import argparse
import copy
import datetime
import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "catalog" / "harness.schema.json"
PRESETS_DIR = ROOT / "catalog" / "presets"
REFERENCE_PATH = ROOT / "docs" / "harness-toml.md"
TEMPLATE_DIR = ROOT / "template"
MANIFEST_PATH = TEMPLATE_DIR / "manifest.toml"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

PRESETS = ("prototype", "poc", "mvp", "small", "large")
THROWAWAY_PRESETS = ("prototype", "poc")
SOURCES = ("preset", "asked", "derived", "open")
MISSING = object()


# --------------------------------------------------------------------------- loading

def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_preset(name: str) -> dict:
    return load_toml(PRESETS_DIR / f"{name}.toml")


# --------------------------------------------------------------------------- paths

def get(data: dict, path: str | tuple, default: Any = MISSING) -> Any:
    keys = path.split(".") if isinstance(path, str) else path
    for key in keys:
        if not isinstance(data, dict) or key not in data:
            return default
        data = data[key]
    return data


def set_path(data: dict, path: tuple, value: Any) -> None:
    for key in path[:-1]:
        data = data.setdefault(key, {})
    data[path[-1]] = value


def dotted(path: tuple) -> str:
    return ".".join(path) or "<root>"


def iter_leaves(schema: dict, path: tuple = ()) -> Iterator[tuple[tuple, dict]]:
    """Yield (path, subschema) for every contract key. A key is a node carrying `x-source`."""
    for key, sub in schema.get("properties", {}).items():
        if "x-source" in sub:
            yield path + (key,), sub
        elif sub.get("type") == "object":
            yield from iter_leaves(sub, path + (key,))


def section_description(schema: dict, path: tuple) -> str:
    node = schema
    for key in path:
        node = node["properties"][key]
    return node.get("description", "")


# --------------------------------------------------------------------------- validation
# Supported JSON Schema subset: type, const, enum, minimum, maximum, minLength, pattern,
# properties, required, additionalProperties (bool or schema), items.

TYPES: dict[str, Callable[[Any], bool]] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}


def validate(value: Any, schema: dict, path: tuple = ()) -> list[str]:
    where = dotted(path)
    expected = schema.get("type")
    if expected and not TYPES[expected](value):
        return [f"{where}: expected {expected}, got {type(value).__name__} ({value!r})"]
    errors = []
    if "const" in schema and value != schema["const"]:
        errors.append(f"{where}: must be {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        allowed = ", ".join(repr(v) for v in schema["enum"])
        errors.append(f"{where}: {value!r} is not one of {allowed}")
    if "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{where}: {value} is below the minimum {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        errors.append(f"{where}: {value} is above the maximum {schema['maximum']}")
    if "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{where}: must not be empty")
    if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
        errors.append(f"{where}: {value!r} does not match {schema['pattern']}")
    if expected == "array":
        for i, item in enumerate(value):
            errors += validate(item, schema.get("items", {}), path + (str(i),))
    if expected == "object":
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{dotted(path + (key,))}: missing required key")
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                errors += validate(item, props[key], path + (key,))
            elif extra is False:
                errors.append(f"{dotted(path + (key,))}: unknown key")
            elif isinstance(extra, dict):
                errors += validate(item, extra, path + (key,))
    return errors


# --------------------------------------------------------------------------- resolution

def deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def resolve(contract: dict, schema: dict) -> dict:
    """Effective contract: preset defaults, overridden by the contract, then defaults and derivations."""
    preset = get(contract, "project.preset", None)
    if preset not in PRESETS:
        raise ValueError(f"project.preset must be one of {', '.join(PRESETS)}, got {preset!r}")
    effective = deep_merge(load_preset(preset), contract)
    for path, sub in iter_leaves(schema):
        if "default" in sub and get(effective, path) is MISSING:
            set_path(effective, path, copy.deepcopy(sub["default"]))
    if get(effective, "agent.hooks.block_git_commit") is MISSING:
        set_path(effective, ("agent", "hooks", "block_git_commit"),
                 not get(effective, "workflow.agent_commits", False))
    order = list(schema["properties"])
    return dict(sorted(effective.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else len(order)))


# --------------------------------------------------------------------------- consistency rules

ERROR, WARNING = "error", "warning"


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    text: str
    broken: Callable[[dict], bool]


def g(c: dict, path: str) -> Any:
    return get(c, path, None)


RULES = [
    Rule("coverage-needs-unit-tests", ERROR,
         "`tests.coverage_min` > 0 requires `tests.unit` other than `off`.",
         lambda c: (g(c, "tests.coverage_min") or 0) > 0 and g(c, "tests.unit") == "off"),
    Rule("tdd-needs-unit-tests", ERROR,
         "`workflow.methodology = \"tdd\"` requires `tests.unit` other than `off`.",
         lambda c: g(c, "workflow.methodology") == "tdd" and g(c, "tests.unit") == "off"),
    Rule("commit-hook-contradiction", ERROR,
         "`agent.hooks.block_git_commit` blocks commits that `workflow.agent_commits` allows.",
         lambda c: g(c, "agent.hooks.block_git_commit") is True and g(c, "workflow.agent_commits") is True),
    Rule("enforced-budgets-need-targets", ERROR,
         "`performance.budgets = \"enforced\"` requires at least one `performance.targets` entry.",
         lambda c: g(c, "performance.budgets") == "enforced" and not g(c, "performance.targets")),
    Rule("commit-rule-not-enforced", WARNING,
         "`workflow.agent_commits = false` without `agent.hooks.block_git_commit`: the rule is only written in AGENTS.md.",
         lambda c: g(c, "workflow.agent_commits") is False and g(c, "agent.hooks.block_git_commit") is False),
    Rule("ci-needs-hosting", WARNING,
         "`ops.ci = true` but `git.hosting = \"none\"`: CI is generated once hosting is chosen.",
         lambda c: g(c, "ops.ci") is True and g(c, "git.hosting") == "none"),
    Rule("cd-needs-ci", WARNING,
         "`ops.cd` is set but `ops.ci = false`: deployments would not be gated.",
         lambda c: g(c, "ops.cd") not in (None, "none") and g(c, "ops.ci") is False),
    Rule("enforced-budgets-need-ci", WARNING,
         "`performance.budgets = \"enforced\"` without `ops.ci`: budgets are only checked locally.",
         lambda c: g(c, "performance.budgets") == "enforced" and g(c, "ops.ci") is False),
    Rule("sensitive-data-needs-security", WARNING,
         "`data.personal = \"sensitive\"` with `security.level` 0.",
         lambda c: g(c, "data.personal") == "sensitive" and (g(c, "security.level") or 0) < 1),
    Rule("personal-data-needs-backups", WARNING,
         "Personal data without `data.backups`.",
         lambda c: g(c, "data.personal") not in (None, "none") and g(c, "data.backups") is False),
    Rule("public-needs-license", WARNING,
         "`project.visibility = \"public\"` with `project.license = \"none\"`.",
         lambda c: g(c, "project.visibility") == "public" and g(c, "project.license") == "none"),
    Rule("spec-driven-needs-plan", WARNING,
         "`workflow.methodology` is spec-driven or tdd but `workflow.plan_before_code = false`.",
         lambda c: g(c, "workflow.methodology") in ("spec-driven", "tdd") and g(c, "workflow.plan_before_code") is False),
    Rule("verify-hook-needs-command", WARNING,
         "`agent.hooks.verify_on_stop = true` but `commands.verify` is not set.",
         lambda c: g(c, "agent.hooks.verify_on_stop") is True and not g(c, "commands.verify")),
]


def apply_rules(effective: dict) -> list[tuple[Rule, str]]:
    return [(rule, rule.text) for rule in RULES if rule.broken(effective)]


# --------------------------------------------------------------------------- template conditions
# Grammar:  expr := and ("or" and)* ; and := not ("and" not)* ; not := "not" not | cmp
#           cmp  := operand (("=="|"!="|">="|"<="|">"|"<"|"in") operand)? ; operand := literal | path | "(" expr ")"
# A path is a dotted key of the render context; a missing path evaluates to None.

class TemplateError(Exception):
    pass


TOKEN = re.compile(r'\s*(?:(?P<num>-?\d+(?:\.\d+)?)|(?P<str>"[^"]*"|\'[^\']*\')|(?P<op>==|!=|>=|<=|>|<|\(|\))'
                   r'|(?P<name>[A-Za-z_][\w.]*))')
COMPARATORS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "in": lambda a, b: a in b,
}
LITERALS = {"true": True, "false": False}


class Condition:
    """A parsed template condition, evaluated against a render context."""

    def __init__(self, text: str):
        self.text = text
        self.tokens = self._tokenize(text)
        self.pos = 0
        self.tree = self._expr()
        if self.pos != len(self.tokens):
            raise TemplateError(f"unexpected {self.tokens[self.pos][1]!r} in condition {text!r}")

    def evaluate(self, context: dict) -> bool:
        return bool(self._eval(self.tree, context))

    # -- parsing
    def _tokenize(self, text: str) -> list[tuple[str, Any]]:
        tokens, pos = [], 0
        while pos < len(text.rstrip()):
            m = TOKEN.match(text, pos)
            if not m or m.end() == pos:
                raise TemplateError(f"cannot parse condition {text!r} at {text[pos:]!r}")
            kind = m.lastgroup
            value = m.group(kind)
            if kind == "num":
                value = float(value) if "." in value else int(value)
            elif kind == "str":
                value = value[1:-1]
            elif kind == "name" and value in ("and", "or", "not", "in"):
                kind = "op"
            tokens.append((kind, value))
            pos = m.end()
        return tokens

    def _peek(self) -> Any:
        return self.tokens[self.pos][1] if self.pos < len(self.tokens) else None

    def _take(self) -> tuple[str, Any]:
        if self.pos >= len(self.tokens):
            raise TemplateError(f"incomplete condition {self.text!r}")
        self.pos += 1
        return self.tokens[self.pos - 1]

    def _expr(self) -> tuple:
        node = self._and()
        while self._peek() == "or":
            self._take()
            node = ("or", node, self._and())
        return node

    def _and(self) -> tuple:
        node = self._not()
        while self._peek() == "and":
            self._take()
            node = ("and", node, self._not())
        return node

    def _not(self) -> tuple:
        if self._peek() == "not":
            self._take()
            return ("not", self._not())
        return self._cmp()

    def _cmp(self) -> tuple:
        left = self._operand()
        if self._peek() in COMPARATORS:
            op = self._take()[1]
            return ("cmp", op, left, self._operand())
        return left

    def _operand(self) -> tuple:
        kind, value = self._take()
        if value == "(" and kind == "op":
            node = self._expr()
            if self._take()[1] != ")":
                raise TemplateError(f"missing ')' in condition {self.text!r}")
            return node
        if kind in ("num", "str"):
            return ("lit", value)
        if kind == "name":
            return ("lit", LITERALS[value]) if value in LITERALS else ("path", value)
        raise TemplateError(f"unexpected {value!r} in condition {self.text!r}")

    # -- evaluation
    def _eval(self, node: tuple, ctx: dict) -> Any:
        kind = node[0]
        if kind == "lit":
            return node[1]
        if kind == "path":
            return get(ctx, node[1], None)
        if kind == "not":
            return not self._eval(node[1], ctx)
        if kind == "and":
            return self._eval(node[1], ctx) and self._eval(node[2], ctx)
        if kind == "or":
            return self._eval(node[1], ctx) or self._eval(node[2], ctx)
        op, left, right = node[1], self._eval(node[2], ctx), self._eval(node[3], ctx)
        try:
            return COMPARATORS[op](left, right)
        except TypeError:
            raise TemplateError(f"cannot apply {op!r} to {left!r} and {right!r} in {self.text!r}") from None


# --------------------------------------------------------------------------- template rendering
# `{{ path }}` is replaced by a context value (missing path → error). Block tags
# `{% if cond %}`, `{% elif cond %}`, `{% else %}`, `{% endif %}` stand alone on their line,
# which is removed from the output. No loops: lists are rendered comma-separated.

BLOCK = re.compile(r"^\s*\{%\s*(if|elif|else|endif)\b(.*?)%\}\s*$")
VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}")


def render_value(value: Any, name: str) -> str:
    if value is MISSING or value is None or isinstance(value, dict):
        raise TemplateError(f"{{{{ {name} }}}}: not a renderable value of the context")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(render_value(v, name) for v in value)
    return str(value)


def render(text: str, context: dict, name: str = "<template>") -> str:
    out: list[str] = []
    stack: list[dict] = []  # open if-blocks: {parent, taken, else}
    active = True
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        where = f"{name}:{number}"
        block = BLOCK.match(line)
        if block:
            tag, expr = block.group(1), block.group(2).strip()
            if tag in ("if", "elif"):
                if not expr:
                    raise TemplateError(f"{where}: {{% {tag} %}} needs a condition")
                condition = Condition(expr)  # parsed even in inactive branches, to catch errors
            if tag == "if":
                taken = active and condition.evaluate(context)
                stack.append({"parent": active, "taken": taken, "else": False})
                active = taken
                continue
            if not stack:
                raise TemplateError(f"{where}: {{% {tag} %}} without {{% if %}}")
            frame = stack[-1]
            if tag in ("elif", "else") and frame["else"]:
                raise TemplateError(f"{where}: {{% {tag} %}} after {{% else %}}")
            if tag == "elif":
                active = frame["parent"] and not frame["taken"] and condition.evaluate(context)
                frame["taken"] |= active
            elif tag == "else":
                active = frame["parent"] and not frame["taken"]
                frame["taken"], frame["else"] = True, True
            else:
                active = stack.pop()["parent"]
            continue
        if "{%" in line:
            raise TemplateError(f"{where}: block tags must stand alone on their line")
        if active:
            try:
                out.append(VARIABLE.sub(lambda m: render_value(get(context, m.group(1)), m.group(1)), line))
            except TemplateError as e:
                raise TemplateError(f"{where}: {e}") from None
    if stack:
        raise TemplateError(f"{name}: {len(stack)} unclosed {{% if %}} block(s)")
    return "".join(out)


def render_context(effective: dict, today: datetime.date | None = None) -> dict:
    """The effective contract plus `harness.*` values available to templates."""
    context = copy.deepcopy(effective)
    context["harness"] = {
        "version": VERSION,
        "date": (today or datetime.date.today()).isoformat(),
        "throwaway": get(effective, "project.preset") in THROWAWAY_PRESETS,
    }
    return context


# --------------------------------------------------------------------------- manifest and generation

FILL = re.compile(r"(?:<!--|#|//)\s*FILL:\s*(.*?)\s*(?:-->|$)")
MANIFEST_KEYS = {"src", "dest", "when"}
NOT_IN_MANIFEST = {"LICENSE", "manifest.toml"}


@dataclass(frozen=True)
class ManifestEntry:
    src: str
    dest: str
    when: Condition | None


def default_dest(src: str) -> str:
    parts = [("." + p[4:]) if p.startswith("dot_") else p for p in src.split("/")]
    dest = "/".join(parts)
    return dest[:-5] if dest.endswith(".tmpl") else dest


def load_manifest() -> list[ManifestEntry]:
    raw = load_toml(MANIFEST_PATH).get("file", [])
    entries = []
    for i, item in enumerate(raw):
        unknown = set(item) - MANIFEST_KEYS
        if unknown or "src" not in item:
            raise TemplateError(f"manifest entry {i + 1}: needs `src`, allows only {sorted(MANIFEST_KEYS)}")
        when = Condition(item["when"]) if item.get("when") else None
        entries.append(ManifestEntry(item["src"], item.get("dest") or default_dest(item["src"]), when))
    return entries


@dataclass
class GeneratedFile:
    dest: str
    src: str
    content: bytes


def generate(effective: dict, today: datetime.date | None = None) -> list[GeneratedFile]:
    """Render every manifest entry whose condition holds. Nothing is written."""
    context = render_context(effective, today)
    files = []
    for entry in load_manifest():
        if entry.when and not entry.when.evaluate(context):
            continue
        source = TEMPLATE_DIR / entry.src
        if entry.src.endswith(".tmpl"):
            content = render(source.read_text(encoding="utf-8"), context, entry.src).encode("utf-8")
        else:
            content = source.read_bytes()
        files.append(GeneratedFile(entry.dest, entry.src, content))
    return files


def lock_data(effective: dict, files: list[GeneratedFile], today: datetime.date | None = None) -> dict:
    """`.harness/lock.json`: what was generated, from which contract and template version."""
    return {
        "harness_version": VERSION,
        "generated_on": (today or datetime.date.today()).isoformat(),
        "contract": effective,
        "files": {f.dest: {"src": f.src, "sha256": hashlib.sha256(f.content).hexdigest()} for f in files},
    }


def write_project(contract_path: Path, dest: Path, schema: dict) -> list[str]:
    """Generate the project into `dest` (must be absent or empty). Returns the written paths."""
    if dest.exists() and any(dest.iterdir()):
        raise TemplateError(f"{dest} is not empty")
    effective = resolve(load_toml(contract_path), schema)
    files = generate(effective)
    extra = {
        "harness.toml": contract_path.read_bytes(),
        ".harness/reference.md": REFERENCE_PATH.read_bytes(),
    }
    lock = lock_data(effective, files)
    extra[".harness/lock.json"] = (json.dumps(lock, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    written = []
    for path, content in [(f.dest, f.content) for f in files] + list(extra.items()):
        target = dest / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        written.append(path)
    return written


def find_fills(root: Path) -> list[tuple[str, int, str]]:
    """(file, line, instruction) of every FILL marker under `root`, skipping .git and .harness."""
    found = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if rel.parts[0] in (".git", ".harness"):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(lines, 1):
            m = FILL.search(line)
            if m:
                found.append((str(rel), number, m.group(1)))
    return found


# --------------------------------------------------------------------------- checks

@dataclass
class Report:
    errors: list[str]
    warnings: list[str]


def check_contract(path: Path, schema: dict) -> Report:
    try:
        contract = load_toml(path)
    except (OSError, tomllib.TOMLDecodeError) as e:
        return Report([f"cannot read contract: {e}"], [])
    errors = validate(contract, schema)
    if errors:
        return Report(errors, [])
    try:
        effective = resolve(contract, schema)
    except ValueError as e:
        return Report([str(e)], [])
    errors = [f"after resolution — {e}" for e in validate(effective, schema)]
    report = Report(errors, [])
    for rule, text in apply_rules(effective):
        (report.errors if rule.severity == ERROR else report.warnings).append(f"[{rule.id}] {text}")
    return report


def sample_contract(preset: str, public: bool = False) -> dict:
    """A contract as the interview would leave it: asked and open keys filled."""
    contract = {"schema_version": 1, "project": {"name": "Sample", "preset": preset},
                "git": {"hosting": "github"}, "commands": {"verify": "make verify"},
                "performance": {"targets": {"example_ms": 1}}}
    if public:
        contract["project"].update(visibility="public", license="MIT", description="A sample.")
        contract["commands"].update({k: f"make {k}" for k in ("install", "dev", "format", "lint",
                                                              "typecheck", "test", "test_e2e")})
        contract["agent"] = {"adapters": ["claude"]}
        contract["data"] = {"personal": "sensitive", "compliance": ["GDPR"]}
    return contract


def check_templates(schema: dict) -> list[str]:
    """Manifest consistency, and every template rendered for every preset."""
    try:
        entries = load_manifest()
    except (TemplateError, OSError, tomllib.TOMLDecodeError) as e:
        return [f"manifest: {e}"]
    errors = [f"manifest: {e.src} does not exist" for e in entries if not (TEMPLATE_DIR / e.src).is_file()]
    listed = {e.src for e in entries}
    for path in sorted(TEMPLATE_DIR.rglob("*")):
        rel = path.relative_to(TEMPLATE_DIR).as_posix()
        if path.is_file() and path.name != ".gitkeep" and rel not in NOT_IN_MANIFEST and rel not in listed:
            errors.append(f"manifest: template/{rel} is not listed")
    dests = [e.dest for e in entries]
    errors += [f"manifest: several entries generate {d}" for d in sorted({d for d in dests if dests.count(d) > 1})]
    if errors:
        return errors
    for name in PRESETS:
        for public in (False, True):
            try:
                generate(resolve(sample_contract(name, public), schema))
            except TemplateError as e:
                errors.append(f"template ({name}, {'public' if public else 'private'}): {e}")
    return errors


def check_catalog(schema: dict) -> Report:
    report = Report([], [])
    leaves = list(iter_leaves(schema))
    for path, sub in leaves:
        if sub.get("x-source") not in SOURCES:
            report.errors.append(f"schema {dotted(path)}: x-source must be one of {', '.join(SOURCES)}")
        if not sub.get("description"):
            report.errors.append(f"schema {dotted(path)}: missing description")
        if sub.get("x-source") in ("asked", "derived", "open") and "default" not in sub \
                and path not in (("project", "name"), ("project", "preset"), ("schema_version",),
                                 ("agent", "hooks", "block_git_commit")):
            report.errors.append(f"schema {dotted(path)}: {sub['x-source']} key needs a default")
        if "default" in sub:
            report.errors += [f"schema default — {e}" for e in validate(sub["default"], sub, path)]
    preset_keys = {path for path, sub in leaves if sub.get("x-source") == "preset"}
    for name in PRESETS:
        try:
            preset = load_preset(name)
        except (OSError, tomllib.TOMLDecodeError) as e:
            report.errors.append(f"preset {name}: cannot read ({e})")
            continue
        partial = {**schema, "required": []}
        report.errors += [f"preset {name}: {e}" for e in validate(preset, partial)]
        for path, sub in leaves:
            present = get(preset, path) is not MISSING
            if path in preset_keys and not present:
                report.errors.append(f"preset {name}: missing {dotted(path)}")
            elif path not in preset_keys and present:
                report.errors.append(f"preset {name}: {dotted(path)} is {sub['x-source']}, not a preset key")
        # Presets must be consistent once the interview has filled asked and open keys.
        for rule, text in apply_rules(resolve(sample_contract(name), schema)):
            if rule.severity == ERROR:
                report.errors.append(f"preset {name}: [{rule.id}] {text}")
    report.errors += check_templates(schema)
    if not REFERENCE_PATH.exists() or REFERENCE_PATH.read_text(encoding="utf-8") != render_reference(schema):
        report.errors.append(f"{REFERENCE_PATH.relative_to(ROOT)} is outdated: run `scripts/harness.py doc`")
    return report


# --------------------------------------------------------------------------- reference doc

def fmt(value: Any) -> str:
    if value is MISSING:
        return ""
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, list):
        return ", ".join(fmt(v) for v in value) or "∅"
    if isinstance(value, dict):
        return ", ".join(f"{k}={fmt(v)}" for k, v in value.items()) or "∅"
    if isinstance(value, str):
        return f"`{value}`" if value else "empty"
    return str(value)


def values_cell(sub: dict) -> str:
    if "enum" in sub:
        return " · ".join(f"`{v}`" for v in sub["enum"])
    kind = sub.get("type", "")
    if kind == "integer" and "minimum" in sub and "maximum" in sub:
        return f"{sub['minimum']}–{sub['maximum']}"
    if kind == "array":
        return f"list of {sub.get('items', {}).get('type', 'values')}"
    if kind == "object":
        return "table"
    return kind


def source_cell(sub: dict) -> str:
    source = sub["x-source"]
    if "default" in sub and source != "preset":
        return f"{source} (default {fmt(sub['default'])})"
    return source


def render_reference(schema: dict) -> str:
    presets = {name: load_preset(name) for name in PRESETS}
    out = [
        "# `harness.toml` reference",
        "",
        "<!-- Generated by `scripts/harness.py doc` from catalog/harness.schema.json and",
        "     catalog/presets/. Do not edit by hand. -->",
        "",
        schema["description"],
        "",
        "Sources: **preset** — default from the chosen preset (columns below) · **asked** — settled",
        "during the interview · **derived** — computed or filled by the AI · **open** — free table.",
        "✓ / ✗ = true / false.",
        "",
    ]
    groups: dict[tuple, list[tuple[tuple, dict]]] = {}
    for path, sub in iter_leaves(schema):
        groups.setdefault(path[:-1], []).append((path, sub))
    for section, leaves in groups.items():
        if not section:  # top level: scalar keys, then each open table as its own section
            for path, sub in leaves:
                if sub.get("type") == "object":
                    out += [f"## `[{path[0]}]` — {sub['x-source']}", "", sub["description"], ""]
                    out += [f"- `{key}`: {prop.get('description', '')}"
                            for key, prop in sub.get("properties", {}).items()]
                else:
                    out += [f"## `{path[0]}` — {sub['x-source']}", "", sub["description"]]
                out.append("")
            continue
        out += [f"## `[{dotted(section)}]`", "", section_description(schema, section), ""]
        out += ["| Key | Values | Source | " + " | ".join(PRESETS) + " |",
                "|---" * (3 + len(PRESETS)) + "|"]
        for path, sub in leaves:
            cells = [fmt(get(presets[p], path)) if sub["x-source"] == "preset" else "" for p in PRESETS]
            out.append(f"| `{path[-1]}` | {values_cell(sub)} | {source_cell(sub)} | " + " | ".join(cells) + " |")
        out.append("")
        for path, sub in leaves:
            line = f"- **`{path[-1]}`** — {sub['description']}"
            if "x-effect" in sub:
                line += f" {sub['x-effect']}"
            out.append(line)
            for value, meaning in sub.get("x-values", {}).items():
                out.append(f"  - `{value}`: {meaning}")
        out.append("")
    out += ["## Consistency rules", "",
            "Checked by `scripts/harness.py check` on the effective contract. Errors make the check",
            "fail; warnings are reported and used by `/upgrade-quality` to challenge changes.", "",
            "| Rule | Severity | Meaning |", "|---|---|---|"]
    out += [f"| `{r.id}` | {r.severity} | {r.text} |" for r in RULES]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- CLI

def print_report(label: str, report: Report) -> None:
    status = "✗" if report.errors else "✓"
    print(f"{status} {label}")
    for e in report.errors:
        print(f"    error: {e}")
    for w in report.warnings:
        print(f"    warning: {w}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="validate the catalog, or the given contracts")
    p_check.add_argument("contracts", nargs="*", type=Path)
    p_resolve = sub.add_parser("resolve", help="print the effective contract as JSON")
    p_resolve.add_argument("contract", type=Path)
    p_doc = sub.add_parser("doc", help="generate the harness.toml reference")
    p_doc.add_argument("--check", action="store_true", help="fail if the reference is outdated")
    p_new = sub.add_parser("new", help="generate a project from a validated contract")
    p_new.add_argument("contract", type=Path)
    p_new.add_argument("--dest", type=Path, required=True, help="project directory (absent or empty)")
    p_new.add_argument("--dry-run", action="store_true", help="list the files without writing them")
    p_fills = sub.add_parser("fills", help="list the FILL markers left in a generated project")
    p_fills.add_argument("dir", type=Path)
    args = parser.parse_args(argv)
    schema = load_schema()

    if args.command == "check":
        if not args.contracts:
            report = check_catalog(schema)
            print_report("catalog", report)
            return 1 if report.errors else 0
        failed = False
        for path in args.contracts:
            report = check_contract(path, schema)
            print_report(str(path), report)
            failed |= bool(report.errors)
        return 1 if failed else 0

    if args.command == "resolve":
        report = check_contract(args.contract, schema)
        if report.errors:
            print_report(str(args.contract), report)
            return 1
        print(json.dumps(resolve(load_toml(args.contract), schema), indent=2, ensure_ascii=False))
        return 0

    if args.command == "new":
        report = check_contract(args.contract, schema)
        print_report(str(args.contract), report)
        if report.errors:
            return 1
        try:
            if args.dry_run:
                files = [f.dest for f in generate(resolve(load_toml(args.contract), schema))]
                paths = files + ["harness.toml", ".harness/reference.md", ".harness/lock.json"]
            else:
                paths = write_project(args.contract, args.dest, schema)
        except TemplateError as e:
            print(f"✗ {e}")
            return 1
        print(("would write" if args.dry_run else "wrote") + f" {len(paths)} files in {args.dest}:")
        for path in paths:
            print(f"    {path}")
        if not args.dry_run:
            print(f"{len(find_fills(args.dest))} FILL markers to replace — `harness.py fills {args.dest}`")
        return 0

    if args.command == "fills":
        fills = find_fills(args.dir)
        for file, line, instruction in fills:
            print(f"{file}:{line}: {instruction}")
        print(f"{len(fills)} FILL marker(s) left")
        return 1 if fills else 0

    rendered = render_reference(schema)
    if args.check:
        current = REFERENCE_PATH.read_text(encoding="utf-8") if REFERENCE_PATH.exists() else ""
        if current != rendered:
            print(f"✗ {REFERENCE_PATH.relative_to(ROOT)} is outdated: run `scripts/harness.py doc`")
            return 1
        print(f"✓ {REFERENCE_PATH.relative_to(ROOT)} is up to date")
        return 0
    REFERENCE_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {REFERENCE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
