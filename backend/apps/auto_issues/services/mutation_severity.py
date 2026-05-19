"""Mutator-name -> AutoIssue severity map for Phase I.

When a mutation tool reports a surviving mutant, the
`file_mutation_survivors` management command files an AutoIssue with
`category='mutation_survivor'` and a severity computed from the mutator
type. High-impact mutators (boundary, equality, return-value, conditional
inversion, arithmetic-zero) get HIGH; arithmetic and logical operator
swaps get MEDIUM; trivial mutators (block-statement removal, string
literal swap, regex flag toggle, void-method-call removal) get LOW.

Per the user policy (2026-05-18): mutation is soft-block locally — every
surviving mutant becomes an AutoIssue that feeds the existing 30-pick
quota. The severity map ensures the picker surfaces dangerous mutants
first, ordered by the existing C++ priority algorithm at
`backend/extensions/autoissue_spam_filter.cpp` (Bayesian classifier;
sources: Sahami et al. 1998, Robinson 2003, MMDS Ch. 13, Bloom 1970)
together with `apps.auto_issues.services.scoring.compute_priority`.

Defaults to MEDIUM for unmapped mutators (defensive). Tools are keyed
by `tool_name` so the same mutator name from different tools (e.g.
Stryker's `BlockStatement` vs. Mull's `block_removal`) can disagree on
severity if needed.
"""

from __future__ import annotations

from apps.auto_issues.models import AutoIssue

# ----- Stryker (Angular) mutator names --------------------------------
# Source: https://stryker-mutator.io/docs/mutation-testing-elements/mutator-list/
_STRYKER_HIGH = {
    "EqualityOperator",          # ==/!=/===/!== swap
    "ConditionalExpression",     # if-true / if-false replacement
    "LogicalOperator",           # &&/|| swap
    "RelationalOperator",        # <,<=,>,>=
    "BooleanLiteral",            # true <-> false swap
    "ReturnStatement",           # return x -> return null/undefined
    "ArithmeticOperator",        # boundary arithmetic
    "UpdateOperator",            # ++ <-> --
    "OptionalChaining",
    "ConditionalAssignment",
}
_STRYKER_LOW = {
    "BlockStatement",            # remove block body
    "StringLiteral",             # "" swap
    "Regex",                     # regex flag toggle
    "ArrayDeclaration",          # [] / [].slice() swap
    "ObjectLiteral",
    "ArrowFunction",
    "MethodExpression",          # void method call removal
}

# ----- mutmut (Python) mutator names ---------------------------------
# Source: https://mutmut.readthedocs.io/en/latest/
_MUTMUT_HIGH = {
    "operator",        # +/-, ==/!=, </>, swap
    "keyword",         # True/False, and/or, is/is not swap
    "number",          # 0/1 <-> 1/2 boundary
    "return",          # return x -> return None
}
_MUTMUT_LOW = {
    "string",          # literal swap
    "decorator",       # decorator removal
    "argument",        # default-arg swap (often equivalent)
}

# ----- Mull (C++) mutator names --------------------------------------
# Source: https://mull.readthedocs.io/en/latest/SupportedMutations.html
_MULL_HIGH = {
    "cxx_lt_to_le",
    "cxx_le_to_lt",
    "cxx_gt_to_ge",
    "cxx_ge_to_gt",
    "cxx_eq_to_ne",
    "cxx_ne_to_eq",
    "cxx_add_to_sub",
    "cxx_sub_to_add",
    "cxx_mul_to_div",
    "cxx_div_to_mul",
    "cxx_logical_and_to_or",
    "cxx_logical_or_to_and",
    "negate_condition",
    "remove_void_call",
    "scalar_value_init_to_zero",
    "replace_scalar_call",
}
_MULL_LOW = {
    "cxx_increment",
    "cxx_decrement",
    "cxx_pre_increment",
    "cxx_pre_decrement",
}

# ----- go-mutesting mutator names ------------------------------------
# Source: https://github.com/zimmski/go-mutesting
_GOMUT_HIGH = {
    "branch/case",
    "branch/if",
    "branch/else",
    "expression/remove",
    "statement/remove",
    "expression/comparison",
}
_GOMUT_LOW = {
    "expression/swap",
}


def _severity_for(tool: str, mutator: str) -> str:
    """Return AutoIssue.SEVERITY_* for the given (tool, mutator)."""
    if tool == "stryker":
        if mutator in _STRYKER_HIGH:
            return AutoIssue.SEVERITY_HIGH
        if mutator in _STRYKER_LOW:
            return AutoIssue.SEVERITY_LOW
    elif tool == "mutmut":
        if mutator in _MUTMUT_HIGH:
            return AutoIssue.SEVERITY_HIGH
        if mutator in _MUTMUT_LOW:
            return AutoIssue.SEVERITY_LOW
    elif tool == "mull":
        if mutator in _MULL_HIGH:
            return AutoIssue.SEVERITY_HIGH
        if mutator in _MULL_LOW:
            return AutoIssue.SEVERITY_LOW
    elif tool in {"go-mutesting", "gomutesting"}:
        if mutator in _GOMUT_HIGH:
            return AutoIssue.SEVERITY_HIGH
        if mutator in _GOMUT_LOW:
            return AutoIssue.SEVERITY_LOW
    # Default: medium for unmapped mutators (defensive).
    return AutoIssue.SEVERITY_MEDIUM


def severity_for(tool: str, mutator: str) -> str:
    """Public alias. Tool is canonical-cased; mutator preserved verbatim."""
    return _severity_for(tool.lower(), mutator)
