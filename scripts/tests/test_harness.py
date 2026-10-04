"""Tests for scripts/harness.py — run with: python3 -m unittest discover -s scripts/tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import harness  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMA = harness.load_schema()

MINIMAL = """
schema_version = 1
[project]
name = "Demo"
preset = "{preset}"
"""


def check(toml_text: str) -> harness.Report:
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8") as f:
        f.write(toml_text)
    try:
        return harness.check_contract(Path(f.name), SCHEMA)
    finally:
        Path(f.name).unlink()


def rule_ids(messages: list[str]) -> set[str]:
    return {m.split("]")[0].lstrip("[") for m in messages if m.startswith("[")}


class CatalogTest(unittest.TestCase):
    def test_catalog_is_valid(self):
        report = harness.check_catalog(SCHEMA)
        self.assertEqual(report.errors, [])

    def test_every_preset_key_is_defined_in_every_preset(self):
        preset_keys = [p for p, s in harness.iter_leaves(SCHEMA) if s["x-source"] == "preset"]
        self.assertGreater(len(preset_keys), 40)
        for name in harness.PRESETS:
            preset = harness.load_preset(name)
            for path in preset_keys:
                self.assertIsNot(harness.get(preset, path), harness.MISSING, f"{name}: {path}")


class ContractTest(unittest.TestCase):
    def test_realistic_contract_is_valid(self):
        report = harness.check_contract(FIXTURES / "budget-mvp.toml", SCHEMA)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_minimal_contract_is_valid_for_every_preset_but_large(self):
        for name in ("prototype", "poc", "mvp", "small"):
            self.assertEqual(check(MINIMAL.format(preset=name)).errors, [], name)

    def test_large_requires_performance_targets(self):
        self.assertEqual(rule_ids(check(MINIMAL.format(preset="large")).errors),
                         {"enforced-budgets-need-targets"})
        with_targets = MINIMAL.format(preset="large") + "[performance.targets]\napi_p95_ms = 300\n"
        self.assertEqual(check(with_targets).errors, [])

    def test_unknown_key_is_rejected(self):
        report = check(MINIMAL.format(preset="mvp") + "[tests]\nsnapshot = true\n")
        self.assertIn("tests.snapshot: unknown key", report.errors)

    def test_value_outside_enum_is_rejected(self):
        report = check(MINIMAL.format(preset="mvp") + '[tests]\nunit = "some"\n')
        self.assertTrue(any(e.startswith("tests.unit:") for e in report.errors), report.errors)

    def test_boolean_is_not_an_integer(self):
        report = check(MINIMAL.format(preset="mvp") + "[tests]\ncoverage_min = true\n")
        self.assertTrue(any("expected integer" in e for e in report.errors), report.errors)

    def test_unknown_preset_is_rejected(self):
        self.assertTrue(check(MINIMAL.format(preset="huge")).errors)

    def test_missing_name_is_rejected(self):
        report = check('schema_version = 1\n[project]\npreset = "mvp"\n')
        self.assertIn("project.name: missing required key", report.errors)

    def test_open_tables_accept_any_key(self):
        text = MINIMAL.format(preset="mvp") + '[stack]\nfirmware = "zephyr"\n[performance.targets]\nram_kb = 256\n'
        self.assertEqual(check(text).errors, [])


class RulesTest(unittest.TestCase):
    def test_coverage_without_unit_tests_is_an_error(self):
        report = check(MINIMAL.format(preset="mvp") + '[tests]\nunit = "off"\n')
        self.assertIn("coverage-needs-unit-tests", rule_ids(report.errors))

    def test_blocking_allowed_commits_is_an_error(self):
        text = MINIMAL.format(preset="mvp") + "[workflow]\nagent_commits = true\n[agent.hooks]\nblock_git_commit = true\n"
        self.assertIn("commit-hook-contradiction", rule_ids(check(text).errors))

    def test_sensitive_data_in_poc_is_a_warning(self):
        report = check(MINIMAL.format(preset="poc") + '[data]\npersonal = "sensitive"\n')
        self.assertEqual(report.errors, [])
        self.assertTrue({"sensitive-data-needs-security", "personal-data-needs-backups"} <= rule_ids(report.warnings))


class ResolveTest(unittest.TestCase):
    def test_preset_then_overrides_then_derived(self):
        contract = harness.load_toml(FIXTURES / "budget-mvp.toml")
        effective = harness.resolve(contract, SCHEMA)
        self.assertEqual(harness.get(effective, "tests.coverage_min"), 80)          # from preset
        self.assertEqual(harness.get(effective, "git.hosting"), "github")         # from contract
        self.assertEqual(harness.get(effective, "project.visibility"), "private")  # schema default
        self.assertIs(harness.get(effective, "agent.hooks.block_git_commit"), True)  # derived
        self.assertEqual(list(effective)[:2], ["schema_version", "project"])

    def test_agent_commits_disables_the_commit_hook(self):
        contract = {"schema_version": 1, "project": {"name": "x", "preset": "poc"},
                    "workflow": {"agent_commits": True}}
        effective = harness.resolve(contract, SCHEMA)
        self.assertIs(harness.get(effective, "agent.hooks.block_git_commit"), False)


class ReferenceTest(unittest.TestCase):
    def test_reference_is_up_to_date(self):
        current = harness.REFERENCE_PATH.read_text(encoding="utf-8")
        self.assertEqual(current, harness.render_reference(SCHEMA),
                         "run `python3 scripts/harness.py doc`")


if __name__ == "__main__":
    unittest.main()
