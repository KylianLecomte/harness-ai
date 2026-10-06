"""Tests for template rendering and project generation — python3 -m unittest discover -s scripts/tests"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import harness  # noqa: E402
from harness import Condition, TemplateError, render  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMA = harness.load_schema()

CTX = {
    "project": {"preset": "mvp", "name": "Demo"},
    "tests": {"unit": "off", "coverage_min": 80},
    "agent": {"adapters": ["claude", "cursor"]},
    "docs": {"adr": True, "roadmap": False},
}


class ConditionTest(unittest.TestCase):
    def ev(self, text):
        return Condition(text).evaluate(CTX)

    def test_comparisons(self):
        self.assertTrue(self.ev('project.preset == "mvp"'))
        self.assertTrue(self.ev("tests.unit != 'critical'"))
        self.assertTrue(self.ev("tests.coverage_min >= 80"))
        self.assertFalse(self.ev("tests.coverage_min > 80"))

    def test_truthiness_and_missing_paths(self):
        self.assertTrue(self.ev("docs.adr"))
        self.assertFalse(self.ev("docs.roadmap"))
        self.assertFalse(self.ev("docs.nothing"))
        self.assertTrue(self.ev("not docs.nothing"))

    def test_boolean_operators_and_precedence(self):
        self.assertTrue(self.ev("docs.roadmap or docs.adr and not docs.roadmap"))
        self.assertFalse(self.ev("(docs.roadmap or docs.adr) and docs.roadmap"))

    def test_membership(self):
        self.assertTrue(self.ev('"claude" in agent.adapters'))
        self.assertFalse(self.ev('"copilot" in agent.adapters'))

    def test_literals(self):
        self.assertTrue(self.ev("docs.adr == true"))

    def test_syntax_errors(self):
        for bad in ('project.preset ==', 'docs.adr docs.roadmap', '(docs.adr', '"x" ? docs', 'and'):
            with self.assertRaises(TemplateError, msg=bad):
                Condition(bad)

    def test_type_error_is_reported(self):
        with self.assertRaises(TemplateError):
            self.ev('project.name > 3')


class RenderTest(unittest.TestCase):
    def test_variables(self):
        self.assertEqual(render("{{ project.name }} / {{agent.adapters}}\n", CTX), "Demo / claude, cursor\n")

    def test_if_elif_else_and_tag_lines_removed(self):
        tpl = ('{% if tests.unit == "all" %}\nA\n{% elif tests.unit == "off" %}\nB\n'
               '{% else %}\nC\n{% endif %}\nend\n')
        self.assertEqual(render(tpl, CTX), "B\nend\n")

    def test_nested_blocks(self):
        tpl = "{% if docs.adr %}\n{% if docs.roadmap %}\nX\n{% else %}\nY\n{% endif %}\n{% endif %}\n"
        self.assertEqual(render(tpl, CTX), "Y\n")

    def test_inactive_branch_does_not_need_its_variables(self):
        self.assertEqual(render("{% if docs.roadmap %}\n{{ missing.key }}\n{% endif %}\n", CTX), "")

    def test_errors(self):
        cases = {
            "missing variable": "{{ missing.key }}\n",
            "table variable": "{{ project }}\n",
            "unclosed": "{% if docs.adr %}\nX\n",
            "orphan endif": "{% endif %}\n",
            "inline tag": "a {% if docs.adr %} b\n",
            "elif after else": "{% if docs.adr %}\n{% else %}\n{% elif docs.adr %}\n{% endif %}\n",
            "if without condition": "{% if %}\n{% endif %}\n",
            "bad condition in inactive branch": "{% if docs.roadmap %}\n{% if == %}\n{% endif %}\n{% endif %}\n",
        }
        for label, tpl in cases.items():
            with self.assertRaises(TemplateError, msg=label):
                render(tpl, CTX)


class ManifestTest(unittest.TestCase):
    def test_default_destination(self):
        self.assertEqual(harness.default_dest("dot_gitignore"), ".gitignore")
        self.assertEqual(harness.default_dest("docs/SPEC.md.tmpl"), "docs/SPEC.md")
        self.assertEqual(harness.default_dest("dot_github/workflows/ci.yml.tmpl"), ".github/workflows/ci.yml")


BASE = {"AGENTS.md", "README.md", ".gitignore", ".editorconfig",
        "docs/SPEC.md", "docs/STACK.md", "docs/CONTEXT.md"}
MVP = BASE | {"docs/ARCHITECTURE.md", "docs/QUALITY.md", "docs/adr/0000-template.md", "docs/adr/0001-stack.md"}
EXPECTED = {
    "prototype": BASE,
    "poc": BASE,
    "mvp": MVP,
    "small": MVP | {"CHANGELOG.md"},
    "large": MVP | {"CHANGELOG.md", "docs/THREAT_MODEL.md"},
}
PUBLIC_EXTRA = {"LICENSE", "CONTRIBUTING.md", "SECURITY.md", "CLAUDE.md"}


class GenerateTest(unittest.TestCase):
    def files(self, preset, public=False):
        effective = harness.resolve(harness.sample_contract(preset, public), SCHEMA)
        return {f.dest: f.content.decode("utf-8") for f in harness.generate(effective)}

    def test_files_per_preset(self):
        for preset, expected in EXPECTED.items():
            self.assertEqual(set(self.files(preset)), expected, preset)
            self.assertEqual(set(self.files(preset, public=True)), expected | PUBLIC_EXTRA, preset)

    def test_no_template_syntax_left(self):
        for preset in harness.PRESETS:
            for public in (False, True):
                for dest, text in self.files(preset, public).items():
                    self.assertNotIn("{{", text, f"{preset}: {dest}")
                    self.assertNotIn("{%", text, f"{preset}: {dest}")

    def test_throwaway_presets_get_light_docs(self):
        poc, mvp = self.files("poc"), self.files("mvp")
        self.assertIn("## Hypothesis", poc["docs/SPEC.md"])
        self.assertNotIn("## Scope", poc["docs/SPEC.md"])
        self.assertNotIn("## Invariants", poc["docs/CONTEXT.md"])
        self.assertIn("## Scope", mvp["docs/SPEC.md"])
        self.assertIn("## Invariants", mvp["docs/CONTEXT.md"])

    def test_contract_drives_the_rules(self):
        agents = self.files("mvp")["AGENTS.md"]
        self.assertIn("**Never run `git commit` or `git push`.**", agents)
        self.assertIn("Spec-driven", agents)
        quality = self.files("small")["docs/QUALITY.md"]
        self.assertIn("≥ 99 %", quality)
        self.assertIn("≤ 12", quality)


class WriteProjectTest(unittest.TestCase):
    def test_writes_project_contract_lock_and_reference(self):
        contract = FIXTURES / "budget-mvp.toml"
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "budgeto"
            written = harness.write_project(contract, dest, SCHEMA)
            self.assertIn("CLAUDE.md", written)
            self.assertEqual((dest / "harness.toml").read_bytes(), contract.read_bytes())
            self.assertTrue((dest / ".harness" / "reference.md").is_file())
            lock = json.loads((dest / ".harness" / "lock.json").read_text(encoding="utf-8"))
            self.assertEqual(lock["harness_version"], harness.VERSION)
            self.assertEqual(lock["contract"]["project"]["name"], "Budgeto")
            for path, info in lock["files"].items():
                self.assertEqual(hashlib.sha256((dest / path).read_bytes()).hexdigest(), info["sha256"], path)
            fills = harness.find_fills(dest)
            self.assertTrue(fills)
            self.assertFalse(any(f[0].startswith(".harness") for f in fills))
            self.assertFalse(any("-->" in f[2] for f in fills), "instructions must not include the comment end")

    def test_refuses_a_non_empty_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "existing.txt").write_text("x")
            with self.assertRaises(TemplateError):
                harness.write_project(FIXTURES / "budget-mvp.toml", Path(tmp), SCHEMA)


if __name__ == "__main__":
    unittest.main()
