"""Tests for the changed-file quality-debt score."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quality_debt_score as qds  # noqa: E402


def score_for(path: str, text: str, extra: dict[str, str] | None = None) -> qds.FileScore:
    """Analyze one in-memory file for duplicate, empty, invalid, and boundary cases."""
    index = {path: text}
    if extra:
        index.update(extra)
    issues = qds.apply_waivers(text, qds.analyze_text(path, text, index))
    return qds.build_file_score(path, True, issues)


def slugs(score: qds.FileScore) -> set[str]:
    """Return issue slugs for duplicate and boundary assertions."""
    return {issue.slug for issue in score.issues}


def test_clean_score_is_100() -> None:
    text = "def add_one(value: int) -> int:\n    return value + 1\n"
    assert score_for("scripts/quality_debt_score.py", text).score == 100.0


def test_baseline_blocks_worse_existing_file(tmp_path: Path) -> None:
    repo = tmp_path
    path = repo / "scripts/example.py"
    path.parent.mkdir()
    path.write_text("def f(a,b,c,d,e,f,g,h):\n    return a\n", encoding="utf-8")
    baseline = {"files": {"scripts/example.py": {"score": 100.0, "issue_count": 0}}}
    text_index = {"scripts/example.py": path.read_text(encoding="utf-8")}
    current = qds.build_file_score(
        "scripts/example.py",
        False,
        qds.analyze_text("scripts/example.py", text_index["scripts/example.py"], text_index),
    )

    failures = qds.file_failures(repo, current, baseline, text_index)

    assert failures


def test_below_90_must_reduce_debt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path
    path = repo / "scripts/example.py"
    path.parent.mkdir()
    path.write_text("def f(a,b,c,d,e,f,g,h):\n    return a\n", encoding="utf-8")
    monkeypatch.setattr(qds, "read_head_text", lambda _repo, _path: path.read_text())
    score = score_for("scripts/example.py", path.read_text())

    failures = qds.file_failures(repo, score, {"files": {}}, {"scripts/example.py": path.read_text()})

    assert failures


def test_documentation_only_passes(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    decision = qds.evaluate_paths(repo, ["README.md"], qds.default_baseline())

    assert decision.passed is True
    assert decision.docs_only is True


def test_waiver_writes_failed_evidence_for_autoissue(tmp_path: Path) -> None:
    decision = qds.GateDecision(
        True,
        "passed",
        [],
        [],
        [
            qds.DebtIssue(
                1,
                "duplicated-code",
                "scripts/example.py",
                1,
                "Repeated block.",
                waiver_reason="temporary compatibility path until split lands",
            )
        ],
        False,
    )
    out = tmp_path / "evidence.jsonl"
    qds.write_evidence(out, decision)

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]

    assert rows[1]["status"] == "failed"
    assert rows[1]["tool_name"] == "quality-debt-waiver"


@pytest.mark.parametrize(
    ("category", "text", "expected"),
    [
        (1, "\n".join(["a = 1", "b = 2", "c = 3", "d = 4", "e = 5", "f = 6"] * 2), "duplicated-code"),
        (2, "def f():\n" + "\n".join("    x = 1" for _ in range(51)), "long-function"),
        (3, "\n".join("x = 1" for _ in range(1501)), "oversized-file"),
        (4, "def f(x):\n" + "\n".join(f"    if x == {i}: pass" for i in range(11)), "high-complexity"),
        (5, "def f(a):\n    if a:\n        for b in a:\n            while b:\n                try:\n                    if b:\n                        pass\n                except Exception:\n                    raise\n", "deep-nesting"),
        (6, "def f(a,b,c,d,e,f,g,h):\n    return a\n", "too-many-inputs"),
        (7, "log(x)\nlog(x)\nlog(x)\n", "repeated-call-pattern"),
        (8, "def a(): pass\ndef b(): pass\ndef c(): pass\ndef d(): pass\n", "generic-owner"),
        (10, "value = a.b.c.d.e\n", "deep-chain"),
        (11, "ROOT = 'C:\\\\temp\\\\file.txt'\n", "hardcoded-path"),
        (12, "items = []\n", "mutable-global"),
        (13, "for row in Item.objects.all():\n    pass\n", "unbounded-query-loop"),
        (14, "while True:\n    work()\n", "unbounded-loop"),
        (15, "class Event(models.Model):\n    name = models.TextField()\n", "unbounded-table-growth"),
        (16, "class Artifact(models.Model):\n    content_hash = models.TextField()\n", "duplicate-artifact"),
        (17, "try:\n    risky()\nexcept Exception:\n    pass\n", "silent-except"),
        (18, "async def f():\n    User.objects.get(id=1)\n", "async-database"),
        (19, "value = eval(user_text)\n", "insecure-input"),
        (20, "SECRET_KEY = '1234567890abcdef'\n", "secret-literal"),
        (21, "def score_value(value):\n    return value\n", "missing-test"),
        (23, "def score_value(value):\n    return value\n", "missing-mutation"),
        (25, "# TODO: fix later\n", "untracked-todo"),
    ],
)
def test_gap_categories(category: int, text: str, expected: str) -> None:
    path = "backend/apps/demo/helpers.py" if category == 8 else "backend/apps/demo/services/example.py"
    score = score_for(path, text)

    assert expected in slugs(score)


def test_category_9_circular_import() -> None:
    text = "from backend.apps.demo.services.two import b\n"
    extra = {"backend/apps/demo/services/two.py": "from backend.apps.demo.services.one import a\n"}

    score = score_for("backend/apps/demo/services/one.py", text, extra)

    assert "circular-import" in slugs(score)


def test_category_22_weak_edge_tests() -> None:
    score = score_for("backend/apps/demo/test_example.py", "def test_happy_path():\n    assert True\n")

    assert "weak-edge-tests" in slugs(score)


def test_category_24_missing_benchmark() -> None:
    score = score_for("backend/extensions/newkernel.cpp", "int score(){ return 1; }\n")

    assert "missing-benchmark" in slugs(score)


def test_new_code_target_failure() -> None:
    score = score_for("backend/apps/demo/services/example.py", "def f(a,b,c,d,e,f,g,h):\n    return a\n")
    failure = qds.file_failures(Path.cwd(), score, qds.default_baseline(), {score.path: ""})

    assert "below 95.0%" in failure[0]


def test_new_code_at_target_does_not_need_old_baseline() -> None:
    score = qds.FileScore(
        "backend/apps/demo/services/example.py",
        True,
        True,
        95.0,
        [qds.DebtIssue(22, "weak-edge-tests", "backend/apps/demo/services/example.py", 1, "x")],
    )

    assert qds.file_failures(Path.cwd(), score, qds.default_baseline(), {score.path: ""}) == []


def test_hook_scripts_call_changed_quality_gate() -> None:
    precommit = Path("scripts/precommit-docker.sh").read_text(encoding="utf-8")
    prepush = Path("scripts/prepush-docker.sh").read_text(encoding="utf-8")

    assert "run-quality-debt-report.sh --changed" in precommit
    assert "run-quality-debt-report.sh --changed" in prepush


def test_git_path_helpers_normalize_changed_and_tracked(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if "ls-files" in command and "--others" not in command:
            return SimpleNamespace(stdout="scripts/a.py\nfrontend/dist/out.js\n", returncode=0)
        return SimpleNamespace(stdout="scripts\\a.py\nREADME.md\n", returncode=0)

    monkeypatch.setattr(qds.subprocess, "run", fake_run)

    assert qds.changed_paths(Path(".")) == ["README.md", "scripts/a.py"]
    assert qds.tracked_source_paths(Path(".")) == ["scripts/a.py"]
    assert len(calls) == 4
    assert all(command[:2] == ["git", "-c"] for command in calls)


def test_file_reading_and_baseline_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    current = tmp_path / "scripts/a.py"
    current.parent.mkdir()
    current.write_text("print('x')\n", encoding="utf-8")
    monkeypatch.setattr(qds.subprocess, "run", lambda *_a, **_k: SimpleNamespace(stdout="old", returncode=0))

    assert qds.read_head_text(tmp_path, "scripts/a.py") == "old"
    assert qds.read_current_text(tmp_path, "scripts/a.py") == "print('x')\n"
    assert qds.read_current_text(tmp_path, "missing.py") == ""
    assert qds.load_baseline(tmp_path / "missing.json")["version"] == 1

    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"version": 99}), encoding="utf-8")
    assert qds.load_baseline(baseline)["files"] == {}


def test_save_baseline_and_build_text_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "scripts/a.py"
    source.parent.mkdir()
    source.write_text("x = 1\n", encoding="utf-8")
    score = qds.FileScore("scripts/a.py", False, True, 100.0, [])
    baseline = tmp_path / ".quality-debt-baseline.json"
    monkeypatch.setattr(qds, "tracked_source_paths", lambda _repo: ["scripts/a.py"])

    qds.save_baseline(baseline, qds.default_baseline(), [score])
    index = qds.build_text_index(tmp_path, ["scripts/a.py"])

    assert "scripts/a.py" in qds.load_baseline(baseline)["files"]
    assert index["scripts/a.py"] == "x = 1\n"
    assert qds.source_hash("scripts/a.py")


def test_explicit_paths_do_not_load_all_tracked_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "scripts" / "a.py"
    source.parent.mkdir()
    source.write_text("def ok():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(
        qds,
        "tracked_source_paths",
        lambda _repo: (_ for _ in ()).throw(AssertionError("unrelated scan")),
    )
    monkeypatch.setattr(qds, "read_head_text", lambda _repo, _path: None)

    decision = qds.evaluate_paths(tmp_path, ["scripts/a.py"], qds.default_baseline())

    assert decision.file_scores[0].path == "scripts/a.py"


def test_explicit_paths_env_accepts_space_separated_staged_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUALITY_DEBT_PATHS", "scripts/a.py scripts/b.py")
    args = SimpleNamespace(paths=[], paths_env="QUALITY_DEBT_PATHS")

    assert qds.explicit_paths(args) == ["scripts/a.py", "scripts/b.py"]


def test_text_index_includes_direct_cpp_benchmark_support(tmp_path: Path) -> None:
    source = tmp_path / "backend" / "extensions" / "newkernel.cpp"
    benchmark = tmp_path / "backend" / "extensions" / "benchmarks" / "bench_newkernel.cpp"
    source.parent.mkdir(parents=True)
    benchmark.parent.mkdir()
    source.write_text("int score(){ return 1; }\n", encoding="utf-8")
    benchmark.write_text("void bench_newkernel() {}\n", encoding="utf-8")

    index = qds.build_text_index(tmp_path, ["backend/extensions/newkernel.cpp"])

    assert "backend/extensions/benchmarks/bench_newkernel.cpp" in index


def test_gate_decision_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "scripts/a.py"
    source.parent.mkdir()
    source.write_text(
        "def f(a,b,c,d,e,f,g,h):\n"
        + "\n".join("    value = 1" for _ in range(51))
        + "\n    return a\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(qds, "tracked_source_paths", lambda _repo: [])
    monkeypatch.setattr(qds, "read_head_text", lambda _repo, _path: "def f(a):\n    return a\n")

    update = qds.evaluate_paths(tmp_path, ["scripts/a.py"], qds.default_baseline(), update_baseline=True)
    decision = qds.evaluate_paths(tmp_path, ["scripts/a.py"], qds.default_baseline())

    assert update.summary == "Baseline updated."
    assert decision.passed is False


def test_file_failure_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    non_strict = qds.FileScore("scripts/a.sh", False, False, 0.0, [])
    improved = qds.FileScore("scripts/a.py", False, True, 85.0, [qds.DebtIssue(2, "x", "scripts/a.py", 1, "x")])
    monkeypatch.setattr(qds, "read_head_text", lambda _repo, _path: None)

    assert qds.file_failures(tmp_path, non_strict, qds.default_baseline(), {}) == []
    assert qds.file_failures(tmp_path, improved, {"files": {"scripts/a.py": {"score": 80, "issue_count": 2}}}, {}) == []


def test_old_file_floor_analyzes_head_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qds, "read_head_text", lambda _repo, _path: "def f(a,b,c,d,e,f,g,h):\n    return a\n")

    old_score, old_count = qds.old_file_floor(tmp_path, "scripts/a.py", qds.default_baseline(), {})

    assert old_score < 100.0
    assert old_count >= 1


def test_extra_scanner_branches() -> None:
    text = "\n".join(
        [
            "from apps.a import x",
            "from apps.b import x",
            "from apps.c import x",
            "from apps.d import x",
            "for row in rows: Item.objects.get(id=row)",
            "try:",
            "    risky()",
            "except Exception:",
            "    logger.warning('failed')",
            "lock = threading.Lock()",
            "# if old_code:",
            "# generated by tool",
            "# do not edit",
        ]
    )
    score = score_for("backend/apps/demo/services/example.py", text)

    found = slugs(score)
    assert "too-many-app-imports" in found
    assert "query-inside-loop" in found
    assert "vague-error" in found
    assert "lock-without-timeout" in found
    assert "commented-code" in found
    assert "generated-output" in found


def test_syntax_and_secret_fallbacks() -> None:
    bad = "SECRET_KEY = '1234567890'\ndef broken(:\n"
    score = score_for("backend/apps/demo/services/example.py", bad)

    assert "syntax-error" in slugs(score)
    assert qds.python_string_literals(bad) == []
    assert qds.has_secret_literal(bad) is True


def test_frontend_test_candidate_and_existing_benchmark() -> None:
    candidates = qds.nearby_test_candidates("frontend/src/app/demo/demo.service.ts")
    text_index = {"backend/extensions/benchmarks/bench_newkernel.cpp": ""}

    benchmark_issues = qds.scan_missing_benchmark("backend/extensions/newkernel.cpp", text_index)

    assert candidates == ["frontend/src/app/demo/demo.service.spec.ts"]
    assert benchmark_issues == []


def test_backend_and_hook_test_candidates() -> None:
    backend_candidates = qds.nearby_test_candidates(
        "backend/apps/auto_issues/management/commands/log_self_review_issue.py"
    )
    hook_candidates = qds.nearby_test_candidates(".githooks/check-registry-read.py")

    assert "backend/apps/auto_issues/tests_log_self_review_issue_command.py" in backend_candidates
    assert ".githooks/test_check_registry_read.py" in hook_candidates


def test_framework_calls_and_string_literals_do_not_create_false_issues() -> None:
    score = score_for("backend/apps/demo/services/example.py", "CATEGORY = 'security'\n")

    assert qds.is_repeated_call_candidate("models.Index(fields=['status'])") is False
    assert "missing-mutation" not in slugs(score)


def test_main_writes_evidence_and_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "scripts" / "quality_debt_score.py"
    test_file = tmp_path / "scripts" / "test_quality_debt_score.py"
    source.parent.mkdir()
    source.write_text("def ok():\n    return 1\n", encoding="utf-8")
    test_file.write_text("# empty invalid boundary duplicate\n", encoding="utf-8")
    monkeypatch.setattr(qds, "tracked_source_paths", lambda _repo: [])
    monkeypatch.setattr(qds, "read_head_text", lambda _repo, _path: None)
    evidence = tmp_path / "evidence.jsonl"
    baseline = tmp_path / "baseline.json"

    status = qds.main(
        [
            "--paths",
            "scripts/quality_debt_score.py",
            "--repo-root",
            str(tmp_path),
            "--baseline",
            str(baseline),
            "--evidence-out",
            str(evidence),
            "--update-baseline",
        ]
    )

    assert status == 0
    assert evidence.exists()
    assert baseline.exists()


def test_main_debt_only_records_failure_without_blocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "scripts" / "quality_debt_score.py"
    source.parent.mkdir()
    source.write_text(
        "def f(a,b,c,d,e,f,g,h):\n"
        + "\n".join("    value = 1" for _ in range(51))
        + "\n    return a\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(qds, "tracked_source_paths", lambda _repo: [])
    monkeypatch.setattr(qds, "read_head_text", lambda _repo, _path: None)
    evidence = tmp_path / "evidence.jsonl"

    status = qds.main(
        [
            "--paths",
            "scripts/quality_debt_score.py",
            "--repo-root",
            str(tmp_path),
            "--evidence-out",
            str(evidence),
            "--debt-only",
        ]
    )

    rows = [json.loads(line) for line in evidence.read_text(encoding="utf-8").splitlines()]
    assert status == 0
    assert rows[0]["status"] == "failed"
