# CITATION-RULE.md — Every Default Has A Source

**Status:** PARAMOUNT for any new feature, setting, ranking signal, meta-algorithm, C++ optimisation, or default value.

## The Rule

Every feature / setting / signal / meta / C++ optimisation / default value MUST have at least one specific citation in `docs/specs/<id>.md`. The CI gate at [`scripts/verify_citations.py`](scripts/verify_citations.py) parses each spec's `Citations:` section and fails the build if any spec is missing one.

## What Counts As A Citation

Specific external references with stable identifiers:
- ✅ DOI (e.g. `10.1145/3077136.3080756`)
- ✅ Patent number (e.g. `US 9,940,367 B1`)
- ✅ RFC number (e.g. `RFC 7932`)
- ✅ Stable public URL with title + author + year (e.g. `Jegou-Douze-Schmid 2010 CVPR — IVFADC`)
- ✅ Peer-reviewed conference / journal paper

What does NOT count:
- ❌ "Common knowledge" or "well-known"
- ❌ "Industry standard"
- ❌ Internal RFCs without a stable public URL
- ❌ Blog post by an AI agent
- ❌ Wikipedia (acceptable as a secondary reference, not as the primary)

## The Spec Citations Section

Every spec at `docs/specs/<id>.md` ends with:

```markdown
## Citations

- Author Year Venue — Title. DOI / URL
- Author Year Venue — Title. DOI / URL
- US Patent NNN,NNN,NNN — Title. Year.
```

For a SETTING or DEFAULT VALUE, the citation must point at a published baseline that justifies the chosen number. Example:

```markdown
- Joachims 2007 TOIS — "Evaluating Retrieval Performance Using Clickthrough Data."
  Cited as the source of the 0.025 default for ctr.ranking_weight; the paper
  shows position-bias-corrected CTR carries ~25 % of the explanatory power of a
  full clickthrough model.
```

For a C++ OPTIMISATION the citation justifies the algorithm choice. Example:

```markdown
- Sivic-Zisserman 2003 ICCV — "Video Google: A Text Retrieval Approach to
  Object Matching in Videos." Source of the inverted-file-index pattern used
  in ivf_index.cpp.
```

## Back-Fill Audit

Existing specs (including the 336 forward-declared stubs from RPT-002) get audited by the CI gate when `verify_citations.py` runs. Any spec missing a `Citations:` section is filed as `RPT-003 — Citation Back-fill` so a future session can populate them.

## Generated Manual

The generated user manual at `docs/MANUAL.md` (built by [`scripts/generate_manual.py`](scripts/generate_manual.py)) reads each spec's frontmatter + Citations section and includes them inline in the manual. Missing citations break the manual build, so the rule is self-enforcing.

## Forbidden Patterns

- ❌ Adding a new ranking weight to `recommended_weights*.py` without an inline comment citing the patent / paper that justifies the value
- ❌ A spec without a `Citations:` section
- ❌ "Heuristic" without explaining what was substituted for the missing primary source
- ❌ Reusing one citation to justify three unrelated choices (each choice needs its own justification)
- ❌ Citing a paywalled paper without including the DOI (operators may not have access; the DOI lets them request via institution)

## Why This Rule Exists

The user is a vibe coder. They can't audit code, but they CAN check whether a default has research behind it. Without citations, defaults are arbitrary and the system's behaviour is mysterious. With citations, every operator-tunable knob has a story: "this is 0.025 because Joachims 2007 §3 measured the position-bias contribution at ~25%."
