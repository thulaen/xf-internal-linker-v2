"""Tests for apps.auto_issues.services.mutation_severity."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.mutation_severity import severity_for


class MutationSeverityTests(SimpleTestCase):
    """severity_for(tool, mutator) maps mutator types to AutoIssue severity."""

    def test_stryker_high_impact_mutators_get_high(self):
        for mutator in ("EqualityOperator", "ConditionalExpression",
                        "ReturnStatement", "BooleanLiteral"):
            self.assertEqual(severity_for("stryker", mutator), AutoIssue.SEVERITY_HIGH,
                             msg=f"{mutator} should be high")

    def test_stryker_low_impact_mutators_get_low(self):
        for mutator in ("BlockStatement", "StringLiteral", "Regex",
                        "ArrayDeclaration"):
            self.assertEqual(severity_for("stryker", mutator), AutoIssue.SEVERITY_LOW,
                             msg=f"{mutator} should be low")

    def test_mutmut_high_impact_mutators_get_high(self):
        for mutator in ("operator", "keyword", "number", "return"):
            self.assertEqual(severity_for("mutmut", mutator), AutoIssue.SEVERITY_HIGH,
                             msg=f"mutmut {mutator} should be high")

    def test_mutmut_low_impact_mutators_get_low(self):
        for mutator in ("string", "decorator", "argument"):
            self.assertEqual(severity_for("mutmut", mutator), AutoIssue.SEVERITY_LOW,
                             msg=f"mutmut {mutator} should be low")

    def test_mull_high_impact_mutators_get_high(self):
        for mutator in ("cxx_lt_to_le", "cxx_eq_to_ne", "cxx_add_to_sub",
                        "negate_condition", "remove_void_call"):
            self.assertEqual(severity_for("mull", mutator), AutoIssue.SEVERITY_HIGH,
                             msg=f"mull {mutator} should be high")

    def test_mull_low_impact_mutators_get_low(self):
        for mutator in ("cxx_increment", "cxx_decrement", "cxx_pre_increment"):
            self.assertEqual(severity_for("mull", mutator), AutoIssue.SEVERITY_LOW,
                             msg=f"mull {mutator} should be low")

    def test_go_mutesting_high_impact_mutators_get_high(self):
        for mutator in ("branch/case", "branch/if", "expression/remove",
                        "expression/comparison"):
            self.assertEqual(
                severity_for("go-mutesting", mutator), AutoIssue.SEVERITY_HIGH,
                msg=f"go-mutesting {mutator} should be high",
            )

    def test_unknown_tool_defaults_to_medium(self):
        self.assertEqual(severity_for("foo-mutator", "anything"),
                         AutoIssue.SEVERITY_MEDIUM)

    def test_unknown_mutator_in_known_tool_defaults_to_medium(self):
        self.assertEqual(severity_for("stryker", "NotAMutatorName"),
                         AutoIssue.SEVERITY_MEDIUM)

    def test_tool_name_is_case_insensitive(self):
        # severity_for() lowercases the tool name internally.
        self.assertEqual(severity_for("Stryker", "EqualityOperator"),
                         AutoIssue.SEVERITY_HIGH)
        self.assertEqual(severity_for("MUTMUT", "operator"),
                         AutoIssue.SEVERITY_HIGH)

    def test_mutator_name_preserved_verbatim(self):
        # Mutator names ARE case-sensitive (regression check).
        # `equalityoperator` is not in the map, so it falls to medium.
        self.assertEqual(severity_for("stryker", "equalityoperator"),
                         AutoIssue.SEVERITY_MEDIUM)

    def test_go_mutesting_low_impact_mutator_gets_low(self):
        self.assertEqual(
            severity_for("go-mutesting", "expression/swap"),
            AutoIssue.SEVERITY_LOW,
        )

    def test_gomutesting_alias_recognized(self):
        self.assertEqual(
            severity_for("gomutesting", "branch/if"),
            AutoIssue.SEVERITY_HIGH,
        )

    def test_cargo_mutants_high_impact_patterns_get_high(self):
        for mutator in (
            "replace function body with Default::default()",
            "replace == with !=",
            "replace + with -",
        ):
            self.assertEqual(
                severity_for("cargo-mutants", mutator),
                AutoIssue.SEVERITY_HIGH,
                msg=f"cargo-mutants {mutator} should be high",
            )

    def test_cargo_mutants_low_impact_patterns_get_low(self):
        for mutator in ("replace += with -=", "replace -= with +="):
            self.assertEqual(
                severity_for("cargo-mutants", mutator),
                AutoIssue.SEVERITY_LOW,
                msg=f"cargo-mutants {mutator} should be low",
            )

    def test_cargo_mutants_unknown_pattern_defaults_to_medium(self):
        self.assertEqual(
            severity_for("cargo-mutants", "replace mystery thing"),
            AutoIssue.SEVERITY_MEDIUM,
        )

    def test_mucheck_high_impact_mutators_get_high(self):
        for mutator in ("ReplaceOp", "NegOp", "IfElseSwap"):
            self.assertEqual(
                severity_for("mucheck", mutator),
                AutoIssue.SEVERITY_HIGH,
                msg=f"mucheck {mutator} should be high",
            )

    def test_mucheck_low_impact_mutators_get_low(self):
        for mutator in ("LiteralSub", "PatternSub"):
            self.assertEqual(
                severity_for("mucheck", mutator),
                AutoIssue.SEVERITY_LOW,
                msg=f"mucheck {mutator} should be low",
            )

    def test_mucheck_unknown_mutator_defaults_to_medium(self):
        self.assertEqual(
            severity_for("mucheck", "UnknownMutation"),
            AutoIssue.SEVERITY_MEDIUM,
        )

    def test_severity_for_returns_string_not_none(self):
        result = severity_for("totally-unknown-tool", "totally-unknown-mutator")
        self.assertIsInstance(result, str)
        self.assertEqual(result, AutoIssue.SEVERITY_MEDIUM)
