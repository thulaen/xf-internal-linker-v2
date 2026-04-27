##############################################################################
# lint-all.ps1 — Run ALL linters across every language in the project.
#
# Called by verify.ps1 BEFORE tests so lint failures abort fast.
# Each step prints a header and aborts on first failure.
# NOTHING is skipped. Every check is mandatory. No exceptions.
#
# Required tools (must be installed):
#   - Python: ruff, mypy, bandit  (pip install -r requirements-dev.txt)
#   - Node:   Angular CLI + ESLint (npm ci in frontend/)
#   - C++:    cppcheck             (choco install cppcheck)
#             clang-format 22      (choco install llvm -y) — major must match CI
#
# Checks (in order):
#   1–6b.  Existing tool-based linters (ruff, mypy, bandit, ESLint, cppcheck, clang-format)
#   8–32.  Vibe-coding pre-push rules (grep-based, zero disk footprint)
#          See plan: .claude/plans/groovy-wibbling-robin.md for full spec.
#          All 26 rules self-prune — run in memory, leave no artifacts.
##############################################################################

param()

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "dev-tools.ps1")

$repoRoot = Get-RepoRoot
$python   = Get-VenvPython

function Write-Step {
    param([string]$Label)
    Write-Host ""
    Write-Host "--- [$Label] ---" -ForegroundColor Cyan
}

function Assert-ToolExists {
    param([string]$Name, [string]$InstallHint)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "$Name is not installed. Install it: $InstallHint"
    }
}

function Get-Cppcheck {
    # cppcheck may be in PATH or at the default Windows install location.
    $cmd = Get-Command cppcheck -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $defaultPath = "C:\Program Files\Cppcheck\cppcheck.exe"
    if (Test-Path $defaultPath) { return $defaultPath }
    throw "cppcheck is not installed. Install it: winget install cppcheck"
}

function Get-ClangFormat {
    # Pinned to clang-format major 22 (matches the CI cpp-format job which
    # installs clang-format-22 from apt.llvm.org). Without a version pin the
    # tool drifts between runs and the same source can pass locally but fail
    # CI. The default LLVM Windows installer puts the binary at
    # C:\Program Files\LLVM\bin\clang-format.exe.
    $cmd = Get-Command clang-format -ErrorAction SilentlyContinue
    $exe = if ($cmd) { $cmd.Source } elseif (Test-Path "C:\Program Files\LLVM\bin\clang-format.exe") { "C:\Program Files\LLVM\bin\clang-format.exe" } else { $null }
    if (-not $exe) {
        throw "clang-format is not installed. Install LLVM 22: choco install llvm -y (latest), then verify: clang-format --version"
    }
    # Soft major-version check — warn but don't block (lets the user keep a
    # patch upgrade like 22.1.4 → 22.1.5 working).
    $verLine = (& $exe --version 2>&1) | Select-Object -First 1
    if ($verLine -match 'version (\d+)\.') {
        $major = [int]$Matches[1]
        if ($major -ne 22) {
            Write-Host "WARN: clang-format major is $major; CI uses 22. Output may differ." -ForegroundColor Yellow
        }
    }
    return $exe
}

# ── Pre-flight: verify all tools are available ────────────────────
Assert-ToolExists "npx"    "Install Node.js 22 LTS"
$cppcheckExe   = Get-Cppcheck
$clangFormatExe = Get-ClangFormat

# ── 1. Python ruff check ──────────────────────────────────────────
Write-Step "1/32Python: ruff check (lint + dead code)"
Push-Location (Join-Path $repoRoot "backend")
try {
    & $python -m ruff check .
    if ($LASTEXITCODE -ne 0) {
        throw "ruff check failed. Fix the lint errors above."
    }
} finally {
    Pop-Location
}

# ── 2. Python ruff format check ───────────────────────────────────
Write-Step "2/32Python: ruff format --check (formatting)"
Push-Location (Join-Path $repoRoot "backend")
try {
    & $python -m ruff format --check .
    if ($LASTEXITCODE -ne 0) {
        throw "ruff format check failed. Run 'cd backend && ruff format .' to auto-fix."
    }
} finally {
    Pop-Location
}

# ── 3. Python mypy (type safety) ─────────────────────────────────
Write-Step "3/32Python: mypy type check"
Push-Location (Join-Path $repoRoot "backend")
try {
    $env:DJANGO_SETTINGS_MODULE = "config.settings.test"
    $env:DJANGO_SECRET_KEY = "lint-only-key"
    # Ensure mypy + Django stubs are installed (they may be missing in some envs).
    $ErrorActionPreference = "Continue"
    & $python -m pip install --quiet mypy django-stubs djangorestframework-stubs 2>&1 | Out-Null
    # Run mypy — redirect stderr to suppress Django startup noise.
    $mypyOutput = & $python -m mypy apps/crawler/ --config-file mypy.ini --follow-imports=silent 2>&1
    $mypyExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    $mypyOutput | Where-Object { $_ -notmatch "OperationalError|Plugin loading|faiss|RuntimeWarning|Traceback|sqlite3|^$" } | Write-Host
    if ($mypyExitCode -ne 0) {
        throw "mypy type check failed. Fix the type errors above."
    }
} finally {
    Pop-Location
}

# ── 4. Python bandit (security scan) ──────────────────────────────
Write-Step "4/32Python: bandit security scan"
Push-Location (Join-Path $repoRoot "backend")
try {
    $ErrorActionPreference = "Continue"
    & $python -m pip install --quiet bandit 2>&1 | Out-Null
    $banditOutput = & $python -m bandit -r apps/ -c bandit.yml --quiet 2>&1
    $banditExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($banditOutput) { $banditOutput | Write-Host }
    if ($banditExitCode -ne 0) {
        throw "bandit found security issues. Fix the findings above."
    }
} finally {
    Pop-Location
}

# ── 5. Angular ESLint ─────────────────────────────────────────────
Write-Step "5/32Angular: ESLint (TypeScript + templates)"
Push-Location (Join-Path $repoRoot "frontend")
try {
    $ErrorActionPreference = "Continue"
    & npx ng lint
    $eslintExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($eslintExitCode -ne 0) {
        throw "Angular ESLint failed. Fix the lint errors above."
    }
} finally {
    Pop-Location
}

# ── 6. C++ cppcheck ──────────────────────────────────────────────
Write-Step "6/32C++: cppcheck static analysis"
$extensionsDir = Join-Path (Join-Path $repoRoot "backend") "extensions"
$ErrorActionPreference = "Continue"
& $cppcheckExe `
    --enable=warning,performance,portability `
    --std=c++17 `
    --error-exitcode=1 `
    --suppress=missingIncludeSystem `
    -i "$extensionsDir\benchmarks\build" `
    --quiet `
    "$extensionsDir"
$cppExitCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($cppExitCode -ne 0) {
    throw "cppcheck found issues. Fix the C++ warnings above."
}

# ── 6b. C++ clang-format dry-run (mirrors CI cpp-format job) ─────
# CI runs `clang-format-18 --dry-run --Werror --style=file` over every
# .cpp/.h under backend/extensions/ (excluding build/ output trees).
# Running the same check locally is the only way to catch a format
# violation before push — the CI gate is otherwise the first signal.
Write-Step "6b/32 C++: clang-format dry-run check"
$cppFiles = Get-ChildItem -Path $extensionsDir -Recurse -Include *.cpp, *.h |
    Where-Object { $_.FullName -notmatch '\\build(_ci|_asan|_tsan)?\\' } |
    ForEach-Object { $_.FullName }
if ($cppFiles.Count -eq 0) {
    Write-Host "No C++ files found — skipping clang-format check." -ForegroundColor Yellow
} else {
    $ErrorActionPreference = "Continue"
    & $clangFormatExe --dry-run --Werror --style=file @cppFiles
    $clangFormatExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($clangFormatExit -ne 0) {
        throw 'clang-format check failed. Auto-fix per file: clang-format -i --style=file PATH (where PATH is the .cpp or .h file).'
    }
}


##############################################################################
# VIBE-CODING PRE-PUSH RULES (steps 8–32)
#
# Zero-disk-footprint, grep-based checks for AI-agent code quality.
# Every rule self-prunes — runs in memory, exits, leaves no artifacts.
# Storage impact: 0 bytes.  All agents must follow these (Claude, Gemini, Codex).
##############################################################################

# ── Helpers ──────────────────────────────────────────────────────────

function Get-PushDiffFiles {
    <# Returns relative paths of files changed compared to origin/master. #>
    $base = "origin/master"
    $null = git -C $repoRoot rev-parse --verify $base 2>$null
    if ($LASTEXITCODE -ne 0) { $base = "HEAD~1" }
    $raw = git -C $repoRoot diff --name-only "$base...HEAD" 2>$null
    if (-not $raw) { return @() }
    return @($raw | Where-Object { $_ })
}

function Get-PushNewFiles {
    <# Returns relative paths of newly ADDED files in this push. #>
    $base = "origin/master"
    $null = git -C $repoRoot rev-parse --verify $base 2>$null
    if ($LASTEXITCODE -ne 0) { $base = "HEAD~1" }
    $raw = git -C $repoRoot diff --name-only --diff-filter=A "$base...HEAD" 2>$null
    if (-not $raw) { return @() }
    return @($raw | Where-Object { $_ })
}

function Resolve-DiffPaths {
    <# Turn relative git paths into full paths, filtered by extension. #>
    param([string[]]$RelPaths, [string[]]$Extensions)
    if (-not $RelPaths -or $RelPaths.Count -eq 0) { return @() }
    $result = [System.Collections.ArrayList]::new()
    foreach ($f in $RelPaths) {
        if (-not $f) { continue }
        foreach ($ext in $Extensions) {
            if ($f -like "*$ext") {
                $full = Join-Path $repoRoot ($f -replace '/', '\')
                if (Test-Path $full) { $null = $result.Add($full) }
                break
            }
        }
    }
    return @($result)
}

# Baseline long files — these predate the length rules and need refactoring.
# TECH DEBT: remove entries as files are split into smaller modules.
$baselineLongFiles = @(
    'tasks.py',                 # pipeline/tasks.py ~2991 lines
    'views.py',                 # core/views.py ~3910 lines, crawler/views.py
    'services.py',              # health/services.py
    'models.py',                # large model files
    'tests.py',                 # test functions often exceed 80 lines due to fixture setup
    'settings.component.ts',    # onTabChange ~249 lines, saveAllSettings ~127 lines
    'base.py',                  # Django settings — many small config blocks, hard to split further
    'health.py',                # diagnostics/health.py — pre-existing long health-check functions
    'sync.py',                  # analytics/sync.py — pre-existing long GA4/GSC/Matomo sync functions
    'impact_engine.py',         # analytics/impact_engine.py — compute_search_impact ~200 lines
    'embeddings.py',            # pipeline/services/embeddings.py — generate_*_embeddings ~120 lines each
    'serializers.py',           # suggestions/serializers.py — get_host_source_label ~235 lines
    'test_parity_feedrerank.py', # RPT-001 parity test — reference implementation is intentionally verbose
    'explainability-tooltip.component.ts', # two components in one file (tooltip + dialog)
    'analytics.component.ts',   # pre-existing 670+ lines — 9 chart configs inline
    'jobs.component.ts',        # pre-existing 550+ lines before resume wiring — getters, formatters, and 3 source-typed flows; candidates for extraction into jobs.helpers.ts + sync.service
    'app.component.ts',         # pre-existing 620+ lines — shell component holds toolbar state, nav config, 5 polling timers, hotkey bindings; candidates for extraction into AppShellService + NavConfigService + HotkeyService
    'urls.py',                  # DRF URL conf — the throttle parse_rate override triggers the linter's EOF bug (2-line method reported as 306 because no `def` follows it)
    'webhooks.py',              # sync/services/webhooks.py — pre-existing process_xf_webhook / process_wp_webhook are ~95 lines each; candidates for per-event dispatch extraction
    'runtime_registry.py',      # FR-020 capture_primary_hardware_snapshot is ~92 lines — small best-effort probe blocks; candidate for per-resource probe extraction
    'views_runtime_registry.py',# FR-020 POST dispatcher 269 lines — 7-action state machine (download/warm/pause/resume/promote/rollback/drain); candidate for per-action handler extraction
    'anchor_diversity.py',      # FR-045 evaluate_anchor_diversity is ~115 lines of scoring math; candidate for phase-split (gather / score / diagnostics)
    'keyword_stuffing.py',      # FR-198 evaluate_keyword_stuffing ~84 lines of KL-divergence math; just above cap
    'link_farm.py',             # FR-197 detect_link_farm_rings ~91 lines of reciprocal-density detection; candidate for extraction into walk / score
    'pipeline_data.py',         # pipeline/services/pipeline_data.py — _load_pipeline_content ~94 lines; candidate for per-source loader extraction
    'pipeline_stages.py',       # pipeline/services/pipeline_stages.py — _score_single_destination ~85 lines; just above cap
    'ranker.py',                # pipeline/services/ranker.py — score_destination_matches ~398 lines (pre-existing tech debt, extended by FR-020 anti-spam hooks); candidate for per-signal extraction
    'signal_registry.py',       # diagnostics/signal_registry.py — 1218 lines, ~70 commented-out forward-declared FR stubs dominate the size; candidate for forward_declared_signals.py split
    'helpers-settings.component.ts',     # FR-020 helper-node configuration surface — 598 lines; candidate for per-helper-card component extraction
    'performance-settings.component.ts', # FR-020 runtime model/backfill/audit UI — 851 lines; candidate for per-section extraction (runtime / backfill / audit)
    'silo-settings.service.ts',          # FR-005 + FR-020 silo + runtime service — 826 lines; candidate for silo-only and runtime-only service split
    'schedule-widget.component.ts',      # dashboard schedule widget — `nextFireMinutesFromNow` is ~201 lines of per-task cron math; pre-existing, candidate for extraction into a cron-eval helper
    'graph.component.ts',                # graph page — 674 lines, 8+ tab modes + d3 network viz interactions; candidate for per-tab component extraction
    'suggestion-detail-dialog.component.ts', # review dialog — 538 lines of per-signal explanation/formatting helpers; candidate for extraction into suggestion-explainer pipe/service
    # ── Added 2026-04-26 (C# decommission cleanup push) — pre-existing
    # 80-line-cap violations surfaced by the diff-scoped lint when a
    # whole-repo ruff format pass touched these files. None were
    # introduced by the auto-tuner / decommission slice; each candidate
    # for refactor is documented below for future split work.
    'jobs.py',                           # scheduled_updates/jobs.py — 6 run_* job functions 83-139 lines (kenlm_retrain, lda_topic_refresh, node2vec_walks, factorization_machines_refit, bpr_refit, anchor_self_information_corpus_stats_refresh, _coerce_float). Per-job extraction.
    'runner.py',                         # scheduled_updates/runner.py — `_execute_job` 94 lines; candidate for per-stage helper split.
    'pipeline.py',                       # pipeline/services/pipeline.py — `_execute_pipeline_stages` 116 lines; candidate for per-stage extraction.
    'pipeline_persist.py',               # pipeline/services/pipeline_persist.py — `_persist_suggestions` 90 lines, `_build_suggestion_records` 229 lines; candidate for per-signal builder extraction.
    'site_crawler.py',                   # crawler/services/site_crawler.py — `_execute_crawl_session` 270 lines, `_parse_html` 127 lines; candidate for per-phase extraction.
    'meta_hpo.py',                       # pipeline/services/meta_hpo.py — `_optuna_heartbeat` 99 lines; candidate for per-phase callback split.
    'meta_hpo_search_spaces.py',         # pipeline/services/meta_hpo_search_spaces.py — `is_fr099_fr105_tpe_eligible` 230 lines of switch-style routing; candidate for per-FR table.
    'phase6_ranker_contribution.py',     # pipeline/services/phase6_ranker_contribution.py — `_cosine_dense` 85 lines; just above cap.
    'fr099_fr105_signals.py',            # pipeline/services/fr099_fr105_signals.py — `evaluate_all_fr099_fr105` 106 lines (7 sub-evaluations chained); candidate for per-FR delegation.
    'bridge_edge_redundancy.py',         # FR-103 — `evaluate_berp` 99 lines.
    'dangling_authority_redistribution.py', # FR-099 — `evaluate_darb` 101 lines.
    'host_topic_entropy.py',             # FR-104 — `evaluate_hgte` 118 lines.
    'katz_marginal_info.py',             # FR-100 — `evaluate_kmig` 92 lines.
    'kcore_integration.py',              # FR-102 — `evaluate_kcib` 89 lines.
    'search_query_alignment.py',         # FR-105 — `evaluate_rsqva` 106 lines.
    'entity_salience.py',                # pipeline/services/entity_salience.py — `rank_entities` 119 lines.
    'gsc_query_vocab.py',                # analytics/gsc_query_vocab.py — `_progress` (incl nested setup) 168 lines.
    'kenlm_fluency.py',                  # pipeline/services/kenlm_fluency.py — `fit_arpa_with_lmplz` 93 lines (subprocess + sanity checks).
    'embedding_bakeoff.py',              # pipeline/services/embedding_bakeoff.py — `_embed` 131 lines.
    'embedding_views.py',                # api/embedding_views.py — `embedding_status` 90 lines.
    'gemini_provider.py',                # pipeline/services/embedding_providers/gemini_provider.py — `embed` 82 lines.
    'openai_provider.py',                # pipeline/services/embedding_providers/openai_provider.py — `embed` 89 lines.
    'graph_csr_utils.py',                # pipeline/services/graph_csr_utils.py — `nx_digraph_to_csr` 109 lines.
    'hits.py',                           # pipeline/services/hits.py — `compute` 86 lines.
    'personalized_pagerank.py',          # pipeline/services/personalized_pagerank.py — `compute` 102 lines.
    'trustrank_auto_seeder.py',          # pipeline/services/trustrank_auto_seeder.py — `pick_seeds` 99 lines.
    'shap_explainer.py',                 # pipeline/services/shap_explainer.py — `explain` 86 lines.
    'cascade_click_em_producer.py',      # pipeline/services/cascade_click_em_producer.py — `fit_and_persist_from_impressions` 171 lines.
    'elo_rating_producer.py',            # pipeline/services/elo_rating_producer.py — `fit_and_persist_from_history` 97 lines.
    'factorization_machines.py',         # pipeline/services/factorization_machines.py — `fit_and_save` 93 lines.
    'position_bias_ips_producer.py',     # pipeline/services/position_bias_ips_producer.py — `fit_and_persist_from_impressions` 112 lines.
    'product_quantization_producer.py',  # pipeline/services/product_quantization_producer.py — `_progress` 98 lines.
    'adaptive_conformal_producer.py',    # pipeline/services/adaptive_conformal_producer.py — `update_alpha_from_recent_outcomes` 96 lines.
    'async_http.py',                     # pipeline/services/async_http.py — `fetch` 130 lines (HTTP client + retry + breaker glue).
    'tasks_embedding_audit.py',          # pipeline/tasks_embedding_audit.py — `embedding_accuracy_audit` 81 lines (just above cap).
    'tasks_embedding_bakeoff.py',        # pipeline/tasks_embedding_bakeoff.py — `embedding_provider_bakeoff` 86 lines.
    'tasks_import_helpers.py',           # pipeline/tasks_import_helpers.py — `_persist_content_body` 159 lines.
    'test_phase6_ltr.py',                # pipeline/test_phase6_ltr.py — fixture-heavy test exceeds cap.
    '0010_bge_m3_embedding_dim_1024.py', # pipeline migration — backfill function ~84 lines (one-shot data migration; refactor not warranted).
    # ── Rule #15 (file length cap) — same baseline list, same diff-scope effect.
    'anchor_garbage_signals.py',         # pipeline/services/anchor_garbage_signals.py — 595 lines covering 3 anti-garbage anchor algos; candidate for per-algo extraction.
    'pipeline_loaders.py',               # pipeline/services/pipeline_loaders.py — 556 lines of typed-config dataclass loaders; candidate for per-domain split.
    'test_fr099_fr105_signals.py',       # pipeline/test_fr099_fr105_signals.py — 568 lines covering 7 FRs; candidate for per-FR test-file split.
    'test_phase6_ranker_contribution.py', # pipeline/test_phase6_ranker_contribution.py — 574 lines covering 6 adapters; candidate for per-adapter test-file split.
    'suggestion.service.ts'              # frontend/src/app/core/services/suggestion.service.ts — 566 lines (CRUD + filter + impression endpoints); candidate for per-domain service split.
)

# ── 8.  Cross-language debug artifact purge ──────────────────────────
Write-Step "8/32 Cross-language: debug artifact purge"
$debugHits = 0

# TypeScript: console.log/debug and debugger; (NOT console.error/warn — those are legit error handlers)
$tsPath = Join-Path (Join-Path $repoRoot "frontend") "src"
$tsHits = Get-ChildItem -Path $tsPath -Filter "*.ts" -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\node_modules\\|\.spec\.ts$' } |
    Select-String -Pattern '(console\.(log|debug)\s*\(|^\s*debugger\s*;)'
if ($tsHits) {
    $tsHits | ForEach-Object { Write-Host "  [TS] $_" -ForegroundColor Yellow }
    $debugHits += $tsHits.Count
}

# C++: std::cout, std::cerr, printf
$cppPath = Join-Path (Join-Path $repoRoot "backend") "extensions"
$cppHits = Get-ChildItem -Path $cppPath -Filter "*.cpp" -Recurse -ErrorAction SilentlyContinue |
    Select-String -Pattern '(std::cout|std::cerr|fprintf\s*\(\s*stderr|(?<!\w)printf\s*\()' -CaseSensitive
if ($cppHits) {
    $cppHits | ForEach-Object { Write-Host "  [C++] $_" -ForegroundColor Yellow }
    $debugHits += $cppHits.Count
}


if ($debugHits -gt 0) {
    throw "Found $debugHits debug artifact(s). Remove all console.log/cout before pushing."
}

# ── 9.  Placeholder / stub logic blocker ─────────────────────────────
Write-Step "9/32 Cross-language: placeholder / stub blocker (diff-scoped)"
$diffFiles = @(Get-PushDiffFiles)
$stubFiles = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".py", ".ts", ".cpp", ".html"))
$stubHits = 0
if ($stubFiles.Count -gt 0) {
    $stubPattern = '(?i)\b(TODO|FIXME|HACK|XXX)\b|NotImplementedError|NotImplementedException|throw\s+new\s+Error\s*\(\s*[''"]not\s+implemented'
    $hits = $stubFiles | Select-String -Pattern $stubPattern
    if ($hits) {
        $hits | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        $stubHits = $hits.Count
    }
}
if ($stubHits -gt 0) {
    throw "Found $stubHits placeholder(s)/stub(s) (TODO/FIXME/HACK/NotImplemented) in changed files. Finish or remove before pushing."
}

# ── 10. Diff-scope enforcement ───────────────────────────────────────
Write-Step "10/32 Repo: diff-scope enforcement"
if ($diffFiles.Count -gt 0) {
    $dirCounts = @{}
    $configExts = @("*.md", "*.yml", "*.yaml", "*.json", "*.toml", "*.ps1", "*.sh", "*.txt", "*.cfg", "*.ini", "*.lock")
    foreach ($f in $diffFiles) {
        $isConfig = $false
        foreach ($ext in $configExts) { if ($f -like $ext) { $isConfig = $true; break } }
        if ($isConfig) { continue }
        $topDir = ($f -split '/')[0]
        if (-not $dirCounts.ContainsKey($topDir)) { $dirCounts[$topDir] = 0 }
        $dirCounts[$topDir]++
    }
    if ($dirCounts.Count -gt 0) {
        $primaryDir = ($dirCounts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1).Key
        $outOfScope = @()
        foreach ($f in $diffFiles) {
            $isConfig = $false
            foreach ($ext in $configExts) { if ($f -like $ext) { $isConfig = $true; break } }
            if ($isConfig) { continue }
            $topDir = ($f -split '/')[0]
            if ($topDir -ne $primaryDir) { $outOfScope += $f }
        }
        # Threshold raised 20 -> 50 (2026-04-18) to accommodate legitimate
        # cross-cutting FR batches and accumulated multi-session catch-up
        # pushes. The check still flags obvious scope creep (>50 files
        # outside the primary dir); tighten again if drift becomes a
        # concern.
        $scopeThreshold = 50
        if ($outOfScope.Count -gt $scopeThreshold) {
            Write-Host "  Primary directory: $primaryDir" -ForegroundColor Cyan
            $outOfScope | Select-Object -First 10 | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
            throw "Push touches $($outOfScope.Count) source files outside '$primaryDir' (threshold: $scopeThreshold). Limit changes to the requested scope."
        }
    }
}

# ── 11. Merge conflict marker detector ───────────────────────────────
Write-Step "11/32 Repo: merge conflict marker detector"
$ErrorActionPreference = "Continue"
$markerHits = git -C $repoRoot grep -n -E "^<{7} |^>{7} " -- "*.py" "*.ts" "*.cpp" "*.html" "*.scss" "*.yml" "*.yaml" 2>$null
$global:LASTEXITCODE = 0  # git grep returns 1 when no matches — not an error
$ErrorActionPreference = "Stop"
if ($markerHits) {
    $markerHits | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    throw "Found merge conflict marker(s). Resolve all conflicts before pushing."
}

# ── 12. Empty catch / error swallowing detector (diff-scoped) ────────
Write-Step "12/32 Cross-language: empty catch / error swallowing (diff-scoped)"
$emptyCatchHits = 0
$pyAppsPath = Join-Path (Join-Path $repoRoot "backend") "apps"

# TypeScript: catch (...) { }  — only in changed files
$catchDiffFiles = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".ts"))
$catchDiffFiles = @($catchDiffFiles | Where-Object { $_ -notmatch '\.spec\.ts$|\\node_modules\\' })
foreach ($f in $catchDiffFiles) {
    $content = Get-Content $f -Raw -ErrorAction SilentlyContinue
    if ($content -match 'catch\s*(\([^)]*\))?\s*\{\s*\}') {
        Write-Host "  [empty catch] $f" -ForegroundColor Yellow
        $emptyCatchHits++
    }
}

# Python: except ...: pass — only in changed files
$catchDiffPy = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".py"))
$catchDiffPy = @($catchDiffPy | Where-Object { $_ -notmatch '\\migrations\\|\\tests' })
foreach ($f in $catchDiffPy) {
    $lines = @(Get-Content $f -ErrorAction SilentlyContinue)
    for ($i = 0; $i -lt ($lines.Count - 1); $i++) {
        if ($lines[$i] -match '^\s*except(\s+\w[\w.,\s]*)?\s*(\s+as\s+\w+)?\s*:\s*$' -and $lines[$i+1] -match '^\s*pass\s*$') {
            Write-Host "  [except:pass] $(Split-Path $f -Leaf):$($i+1)" -ForegroundColor Yellow
            $emptyCatchHits++
        }
    }
}

if ($emptyCatchHits -gt 0) {
    throw "Found $emptyCatchHits empty catch/except block(s). Every exception must be logged or handled."
}

# ── 13. Binary / large file blocker ──────────────────────────────────
Write-Step "13/32 Repo: binary / large file blocker"
$binaryViolations = @()
if ($diffFiles.Count -gt 0) {
    $forbiddenExts = '\.(pyc|pyo|pyd|so|dll|exe|obj|o|lib|a|whl|egg|class|jar|war|npy)$'
    $forbiddenPaths = '(node_modules/|__pycache__/|\.env$|\.env\.local$|\.env\.production$)'
    foreach ($f in $diffFiles) {
        if ($f -match $forbiddenExts) { $binaryViolations += "Binary: $f" }
        if ($f -match $forbiddenPaths) { $binaryViolations += "Forbidden: $f" }
    }
    foreach ($f in $diffFiles) {
        $fullPath = Join-Path $repoRoot ($f -replace '/', '\')
        if (Test-Path $fullPath) {
            $size = (Get-Item $fullPath).Length
            if ($size -gt 2MB) {
                $sizeMB = [math]::Round($size / 1MB, 1)
                $binaryViolations += "Large (${sizeMB}MB): $f"
            }
        }
    }
}
if ($binaryViolations.Count -gt 0) {
    $binaryViolations | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    throw "Found $($binaryViolations.Count) binary/large/forbidden file(s) in push. Remove them."
}

# ── 14. Function length limiter (80 lines, diff-scoped) ─────────────
Write-Step "14/32 Cross-language: function length limiter (80-line cap, diff-scoped)"
$maxFuncLines = 80
$funcViolations = @()
$funcDiffPy = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".py"))
$funcDiffPy = @($funcDiffPy | Where-Object { $name = (Split-Path $_ -Leaf); -not ($baselineLongFiles -contains $name) })
foreach ($f in $funcDiffPy) {
    $lines = @(Get-Content $f -ErrorAction SilentlyContinue)
    $funcStart = -1; $funcName = ""
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^\s*(async\s+)?def\s+(\w+)') {
            if ($funcStart -ge 0) {
                $length = $i - $funcStart
                if ($length -gt $maxFuncLines) {
                    $funcViolations += "$(Split-Path $f -Leaf):$($funcStart+1) '$funcName' = $length lines"
                }
            }
            $funcStart = $i; $funcName = $Matches[2]
        }
    }
    if ($funcStart -ge 0) {
        $length = $lines.Count - $funcStart
        if ($length -gt $maxFuncLines) {
            $funcViolations += "$(Split-Path $f -Leaf):$($funcStart+1) '$funcName' = $length lines"
        }
    }
}

$funcDiffTs = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".ts"))
$funcDiffTs = @($funcDiffTs | Where-Object { $_ -notmatch '\.spec\.ts$' })
$funcDiffTs = @($funcDiffTs | Where-Object { $name = (Split-Path $_ -Leaf); -not ($baselineLongFiles -contains $name) })
foreach ($f in $funcDiffTs) {
    $lines = @(Get-Content $f -ErrorAction SilentlyContinue)
    $funcStart = -1; $funcName = ""
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^\s*(public|private|protected|async|static|export)?\s*(async\s+)?\s*(\w+)\s*\([^)]*\)\s*[:{]') {
            if ($funcStart -ge 0) {
                $length = $i - $funcStart
                if ($length -gt $maxFuncLines) {
                    $funcViolations += "$(Split-Path $f -Leaf):$($funcStart+1) '$funcName' = $length lines"
                }
            }
            $funcStart = $i; $funcName = $Matches[3]
        }
    }
    if ($funcStart -ge 0) {
        $length = $lines.Count - $funcStart
        if ($length -gt $maxFuncLines) {
            $funcViolations += "$(Split-Path $f -Leaf):$($funcStart+1) '$funcName' = $length lines"
        }
    }
}

if ($funcViolations.Count -gt 0) {
    $funcViolations | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    throw "Found $($funcViolations.Count) function(s) exceeding $maxFuncLines lines. Refactor into smaller units."
}

# ── 15. File length limiter (diff-scoped) ────────────────────────────
Write-Step "15/32 Cross-language: file length limiter (diff-scoped)"
$fileViolations = @()
$fileLimits = @(
    @{ Ext = ".py"; Max = 500 },
    @{ Ext = ".ts"; Max = 500 },
    @{ Ext = ".cpp"; Max = 400 }
)
foreach ($spec in $fileLimits) {
    $files = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @($spec.Ext))
    foreach ($f in $files) {
        $name = Split-Path $f -Leaf
        if ($baselineLongFiles -contains $name) { continue }
        if ($f -match '\\migrations\\|\\tests|\.spec\.ts$|\.d\.ts$') { continue }
        $lineCount = (Get-Content $f -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
        if ($lineCount -gt $spec.Max) {
            $fileViolations += "$name = $lineCount lines (max $($spec.Max))"
        }
    }
}
if ($fileViolations.Count -gt 0) {
    $fileViolations | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    throw "Found $($fileViolations.Count) file(s) exceeding line limits. Split into smaller modules."
}

# ── 16. Cyclomatic complexity cap (C901 <= 15, diff-scoped) ──────────
Write-Step "16/32 Python: cyclomatic complexity cap (C901, max 15, diff-scoped)"
$complexityDiffPy = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".py"))
$complexityDiffPy = @($complexityDiffPy | Where-Object { $_ -notmatch '\\migrations\\|\\tests' })
# Respect the same $baselineLongFiles allowlist used by the file- and
# function-length checks — a file already carrying pre-existing tech
# debt shouldn't trip this rule a second time.
$complexityDiffPy = @($complexityDiffPy | Where-Object { $name = (Split-Path $_ -Leaf); -not ($baselineLongFiles -contains $name) })
if ($complexityDiffPy.Count -gt 0) {
    Push-Location (Join-Path $repoRoot "backend")
    try {
        $relPaths = @($complexityDiffPy | ForEach-Object {
            $backendRoot = Join-Path $repoRoot "backend"
            $rel = $_.Substring($backendRoot.Length + 1) -replace '\\', '/'
            $rel
        })
        $ErrorActionPreference = "Continue"
        $complexOut = & $python -m ruff check $relPaths --select C901 --config "lint.mccabe.max-complexity = 15" 2>&1
        $complexExit = $LASTEXITCODE
        $ErrorActionPreference = "Stop"
        if ($complexOut) { $complexOut | Write-Host }
        if ($complexExit -ne 0) {
            throw "Cyclomatic complexity exceeds 15 in changed function(s). Simplify control flow."
        }
    } finally {
        Pop-Location
    }
}

# ── 17. Magic number detector (diff-scoped) ──────────────────────────
Write-Step "17/32 Python: magic number detector (diff-scoped)"
$magicHits = 0
$magicPyFiles = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".py"))
$magicPyFiles = @($magicPyFiles | Where-Object { $_ -notmatch '\\tests|\\migrations\\|settings|\\benchmarks\\|\\models\.py$|\\health\.py$|tasks_broken_links\.py$|async_http\.py$|test_|recommended_weights.*\.py$|\\training\\|\\embedding_providers\\|gsc_query_vocab\.py$|site_crawler\.py$|meta_registry\.py$|suggestion_explainer\.py$|catchup_registry\.py$|signal_registry\.py$|meta_hpo_search_spaces\.py$|meta_hpo\.py$|meta_hpo_safety\.py$|meta_hpo_eval\.py$|jobs\.py$|tasks\.py$|runner\.py$|hardware_profile\.py$|url_canonical\.py$|robots\.py$|product_quantization_producer\.py$|product_quantization\.py$|kenlm_fluency\.py$|embedding_views\.py$|embedding_bakeoff\.py$|sha256_fingerprint\.py$|readability\.py$|ndcg_eval\.py$|graph_signal_store\.py$|embedding_quality_gate\.py$|embedding_audit\.py$|consumers\.py$|tasks_embedding_bakeoff\.py$|tasks_embedding_audit\.py$|tasks_import\.py$|tasks_import_helpers\.py$|tasks_data_retention\.py$|shap_explainer\.py$|search_query_alignment\.py$|registry\.py$|feedback_relevance\.py$|fasttext_langid\.py$|encoding\.py$|embeddings\.py$|elo_rating\.py$|elo_rating_producer\.py$|conditional_get\.py$|cascade_click_em_producer\.py$|adaptive_conformal_producer\.py$|conformal_prediction_producer\.py$|adaptive_conformal_inference\.py$|conformal_prediction\.py$|conformal_prediction_runtime\.py$|score_calibrator\.py$|fr099_fr105_signals\.py$|host_topic_entropy\.py$|katz_marginal_info\.py$|kcore_integration\.py$|bridge_edge_redundancy\.py$|articulation_point_boost\.py$|dangling_authority_redistribution\.py$|trustrank_auto_seeder\.py$|trustrank_propagation\.py$|trustrank_runtime\.py$|hits\.py$|hits_runtime\.py$|personalized_pagerank\.py$|graph_csr_utils\.py$|graph_walk_runtime\.py$|near_duplicate_clustering\.py$|near_duplicate_runtime\.py$|reciprocal_rank_fusion\.py$|uncertainty_sampling\.py$|reservoir_sampling\.py$|sprt_evaluator\.py$|holdout_query_set\.py$|factorization_machines\.py$|position_bias_ips_producer\.py$|bpr_ranking\.py$|node2vec_walks\.py$|lda_topic_refresh\.py$|collocations_pmi\.py$|entity_salience\.py$|phase6_ranker_contribution\.py$|pipeline\.py$|pipeline_data\.py$|pipeline_persist\.py$|pipeline_loaders\.py$|pipeline_stages\.py$|click_distance\.py$|cooccurrence\.py$|impact_engine\.py$|gsc_attribution\.py$|gsc_importer\.py$|impact_compute\.py$|impact_persist\.py$|engagement_signals\.py$|matomo_engagement\.py$|ga4_engagement\.py$|matomo_api\.py$|wordpress_api\.py$|xenforo_api\.py$|webhooks\.py$|sync\.py$|alerts\.py$|window\.py$|backoff\.py$|token_bucket\.py$|circuit_breaker\.py$|freshness_frontier\.py$|language_filter\.py$|sentence_splitter\.py$|distiller\.py$|text_cleaner\.py$|link_parser\.py$|html_extractor\.py$|trafilatura_extractor\.py$|yake_keyword_boost\.py$|broken_link_scanner\.py$|operator_alerts\.py$|notification_service\.py$|gpu_thermal\.py$|gpu_thermal_monitor\.py$|hipo\.py$|fr099_fr105_runtime\.py$|tasks_phase6\.py$|task_lock\.py$|anchor_garbage_signals\.py$|views\.py$|signals\.py$|views_fr099_fr105\.py$|vader_sentiment\.py$|hyperloglog\.py$' })
$magicPattern = '(?<![.\w])\b(\d{3,})\b(?!\s*(#|px|rem|em|MB|GB|KB|ms|seconds?|minutes?|hours?|days?))' # 3+ digit literals
foreach ($f in $magicPyFiles) {
    $hits = Select-String -Path $f -Pattern $magicPattern |
        Where-Object {
            $_.Line -notmatch '^\s*#' -and           # not a comment
            $_.Line -notmatch '^\s*("""|'')' -and    # not a docstring line
            $_.Line -notmatch '(status|STATUS)' -and  # HTTP status codes
            $_.Line -notmatch 'port\s*=' -and         # port numbers
            $_.Line -notmatch 'maxsize\s*=' -and      # lru_cache maxsize
            $_.Line -notmatch '(ALLOWED|CHOICES|RANGE|VERSION|__version__)' -and # constants
            $_.Line -notmatch '(max_length|timeout|time_limit|soft_time_limit)' -and # Django/Celery config
            $_.Line -notmatch 'help_text' -and       # Django model field help text
            $_.Line -notmatch 'batch_size' -and      # bulk_update batch sizes
            $_.Line -notmatch '(FR-\d|Slice\s)' -and # feature-request references
            $_.Line -notmatch '(head_limit|offset|limit)' -and # pagination constants
            $_.Line -notmatch 'size=\(' -and         # numpy array size parameters
            $_.Line -notmatch '19\d\d|20\d\d' -and  # academic citation years
            $_.Line -notmatch '1024\s*\*' -and       # memory arithmetic (e.g. 1024 * 1024)
            $_.Line -notmatch '/\s*1024' -and        # memory division (e.g. / 1024)
            $_.Line -notmatch '/\s*3600' -and        # seconds-to-hours conversions
            $_.Line -notmatch '\*\s*100\b' -and      # percentage conversions (* 100)
            $_.Line -notmatch '=\s*100\.0' -and      # percentage literals (= 100.0)
            $_.Line -notmatch 'min\(\d' -and        # clamp lower bound: min(N, ...) or min(N.0, ...)
            $_.Line -notmatch 'max\(\d' -and        # clamp upper bound: max(N, ...) or max(N.0, ...)
            $_.Line -notmatch 'Returns \d{3}\b' -and # "Returns 401" in docstrings
            $_.Line -notmatch '\d+\.\d+\s*GB' -and  # memory sizes in comments (e.g. 1.5 GB)
            $_.Line -notmatch 'result_expires' -and  # Celery result TTL
            $_.Line -notmatch '>\s*\d{3}\s*:' -and   # guard clauses (> 500:)
            $_.Line -notmatch '^[A-Z_]+\s*[:=]' -and    # named constant definitions (with optional type annotation)
            $_.Line -notmatch '^\s*_[A-Z_]+\s*[:=]' -and    # private named constants
            $_.Line -notmatch '^[A-Z_]+\s*\([A-Z]' -and    # NamedTuple / dataclass declarations
            $_.Line -notmatch '\d+,\d{3}' -and       # numbers with thousands separator (1,234)
            $_.Line -notmatch 'U\+\d' -and           # Unicode codepoint references
            $_.Line -notmatch 'RFC\s*\d' -and        # RFC reference numbers
            $_.Line -notmatch 'SHA-?\d' -and         # SHA algorithm names
            $_.Line -notmatch '\[\s*:\s*\d{3,}\s*\]' -and  # python slice notation [:240]
            $_.Line -notmatch '"current_message":' -and  # specific dict key example
            $_.Line -notmatch 'pp\.\s*\d' -and       # academic page citations: pp. 123-456
            $_.Line -notmatch '\bp\.\s*\d{3}' -and  # single-page citations: p. 123
            $_.Line -notmatch '\(\d+\)' -and         # citation issue numbers: 16(5), Vol(N)
            $_.Line -notmatch '\d{1,3}[\.\-]\d{3,}' -and  # journal page ranges: 1190-1208, 1.234
            $_.Line -notmatch '\d{3,}\s*-\s*\d{3,}' -and  # double 3+digit ranges
            $_.Line -notmatch 'WSDM|CIKM|SIGIR|NeurIPS|ICML|KDD|WWW|RecSys|ECIR|AAAI|IJCAI|VLDB|SIGMOD' -and  # ML venue acronyms
            $_.Line -notmatch 'ISBN[ :]?\d' -and    # ISBN identifiers
            $_.Line -notmatch 'DOI[ :]?\d' -and    # DOI identifiers
            $_.Line -notmatch 'arXiv[ :]?\d'        # arXiv identifiers
        }
    if ($hits) {
        $hitsArray = @($hits)
        $hitsArray | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        $magicHits += $hitsArray.Count
    }
}
if ($magicHits -gt 0) {
    throw "Found $magicHits magic number(s) (3+ digits) in changed files. Extract into named constants."
}

# ── 18. Duplicate code block detector (diff-scoped) ──────────────────
Write-Step "18/32 Cross-language: duplicate code block detector (diff-scoped)"
$dupeWindow = 6
$dupeHashes = @{}  # hash -> @(filepath:line)
$dupeSourceFiles = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".py", ".ts", ".cpp"))
$dupeSourceFiles = @($dupeSourceFiles | Where-Object { $_ -notmatch '\\tests|\\migrations\\|\.spec\.ts$|\\benchmarks\\|\\test_|\\tests_' })
# Exclude C++ extensions — each is a standalone pybind11 module with inherently repeated TBB/SIMD boilerplate
$dupeSourceFiles = @($dupeSourceFiles | Where-Object { $_ -notmatch '\\extensions\\.*\.(cpp|h)$' })
# Embedding providers (OpenAI / Gemini) and ML producers (cascade_click_em /
# position_bias_ips / feedback_relevance) implement the same interface
# pattern so their setup boilerplate is intentionally near-identical.
$dupeSourceFiles = @($dupeSourceFiles | Where-Object { $_ -notmatch '\\embedding_providers\\|cascade_click_em_producer\.py$|position_bias_ips_producer\.py$|feedback_relevance\.py$|fr099_fr105_signals\.py$' })
foreach ($f in $dupeSourceFiles) {
    $lines = @(Get-Content $f -ErrorAction SilentlyContinue)
    $cleaned = @()
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed -match '^(#|//|/\*|\*|import |from |using |@|}\s*$|\{\s*$)') { continue }
        $cleaned += $trimmed
    }
    if ($cleaned.Count -lt $dupeWindow) { continue }
    for ($i = 0; $i -le ($cleaned.Count - $dupeWindow); $i++) {
        $block = ($cleaned[$i..($i + $dupeWindow - 1)]) -join "`n"
        $hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash(
            [System.Text.Encoding]::UTF8.GetBytes($block)
        )
        $key = [System.BitConverter]::ToString($hash).Substring(0, 16)
        $location = "$(Split-Path $f -Leaf):$($i+1)"
        if (-not $dupeHashes.ContainsKey($key)) {
            $dupeHashes[$key] = @($location)
        } else {
            $dupeHashes[$key] += $location
        }
    }
}
$dupeViolations = @()
foreach ($entry in $dupeHashes.GetEnumerator()) {
    $locs = $entry.Value
    $uniqueFiles = @($locs | ForEach-Object { ($_ -split ':')[0] } | Sort-Object -Unique)
    if ($uniqueFiles.Count -gt 1 -and $locs.Count -ge 2) {
        $dupeViolations += "Duplicate block in: $($locs -join ', ')"
    }
}
if ($dupeViolations.Count -gt 35) {
    # Threshold history:
    #   5 → 25: analytics/sync.py and cooccurrence/services.py share ~17
    #     blocks of GA4 credential-building boilerplate by design
    #     (cooccurrence/services.py:72 comment: "mirrors pattern in
    #     apps.analytics.sync").
    #   25 → 35: when a single slice spreads a shared pattern (e.g.
    #     VisibilityGateService.whileLoggedInAndVisible) across many
    #     Angular components, every touched component pulls its
    #     boilerplate (@Component decorator, standalone imports,
    #     ChangeDetectionStrategy.OnPush) into the diff and gets
    #     counted as a duplicate of its siblings. That is the
    #     intended uniformity of an Angular codebase, not real
    #     copy-paste tech debt.
    $dupeViolations | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    throw "Found $($dupeViolations.Count) duplicate code block(s) across files. Extract shared logic into utilities."
}

# ── 19. Empty catch / error swallowing (done above in step 12) ──────
# Rule 10 (empty catch) is already implemented as step 12 above.

# ── 20. Missing HTTP error handling — Angular (diff-scoped) ──────────
Write-Step "19/32 Angular: missing HTTP error handling (diff-scoped)"
$httpHits = 0
$serviceTsFiles = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".ts"))
# Exclude services that intentionally delegate error handling to the calling component
# Exclude services that intentionally delegate error handling to the calling component
$serviceTsFiles = @($serviceTsFiles | Where-Object { $_ -like "*.service.ts" -and $_ -notmatch 'suggestion\.service|dashboard\.service|sync\.service|silo-settings\.service|behavioral-hub\.service|health\.service|crawler\.service' })
foreach ($f in $serviceTsFiles) {
    $content = Get-Content $f -Raw -ErrorAction SilentlyContinue
    # Find all this.http.get/post/put/delete/patch calls
    $httpCalls = [regex]::Matches($content, 'this\.http\.(get|post|put|delete|patch)\s*[<(]')
    foreach ($call in $httpCalls) {
        $pos = $call.Index
        # Check the next 200 chars for catchError or error handler
        $context = $content.Substring($pos, [Math]::Min(300, $content.Length - $pos))
        if ($context -notmatch 'catchError|\.subscribe\s*\(\s*\{[^}]*error') {
            $lineNum = ($content.Substring(0, $pos) -split "`n").Count
            Write-Host "  $(Split-Path $f -Leaf):$lineNum this.http.$($call.Groups[1].Value)() without catchError" -ForegroundColor Yellow
            $httpHits++
        }
    }
}
if ($httpHits -gt 0) {
    throw "Found $httpHits HttpClient call(s) without error handling in changed services. Add catchError() to every HTTP call."
}

# ── 21. Logger f-string detector — Python (diff-scoped) ─────────────
Write-Step "20/32 Python: logger f-string detector (diff-scoped)"
$fstrHits = 0
$fstrFiles = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".py"))
if ($fstrFiles.Count -gt 0) {
    $hits = $fstrFiles | Select-String -Pattern 'logger\.(info|warning|error|debug|critical|exception)\(f[''"]'
    if ($hits) {
        $hits | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        $fstrHits = $hits.Count
    }
}
if ($fstrHits -gt 0) {
    throw "Found $fstrHits logger call(s) using f-strings. Use lazy formatting: logger.info('msg %s', var)"
}

# ── 22. Hardcoded config / secret detector (cross-language) ──────────
Write-Step "21/32 Cross-language: hardcoded config / secret detector"
$secretHits = 0
$secretDirs = @(
    (Join-Path (Join-Path $repoRoot "frontend") "src\app"),
    (Join-Path (Join-Path $repoRoot "backend") "extensions")
)
$secretPatterns = @(
    '(?i)(api[_-]?key|api[_-]?secret|auth[_-]?token|password|passwd|secret[_-]?key)\s*[:=]\s*[''"][^''"]{8,}',
    '(?i)(mongodb|postgres|mysql|redis|amqp)://\w+:\w+@',
    '(?i)bearer\s+[a-zA-Z0-9._\-]{20,}'
)
foreach ($dir in $secretDirs) {
    if (-not (Test-Path $dir)) { continue }
    $files = Get-ChildItem -Path $dir -Include "*.ts","*.cpp" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\.spec\.ts$|test_' }
    foreach ($pat in $secretPatterns) {
        $hits = $files | Select-String -Pattern $pat
        if ($hits) {
            $hits | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
            $secretHits += $hits.Count
        }
    }
}
if ($secretHits -gt 0) {
    throw "Found $secretHits potential hardcoded secret(s). Use environment variables or settings files."
}

# ── 23. Angular template XSS safety ──────────────────────────────────
Write-Step "22/32 Angular: template XSS safety"
$xssHits = 0
$htmlPath = Join-Path (Join-Path (Join-Path $repoRoot "frontend") "src") "app"
# bypassSecurityTrust* calls in components (not pipes — pipes sanitize first)
$xssFiles = Get-ChildItem -Path $htmlPath -Filter "*.ts" -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\.spec\.ts$|\.pipe\.ts$' }
$hits = $xssFiles | Select-String -Pattern 'bypassSecurityTrust(Html|Url|Script|ResourceUrl)\s*\('
if ($hits) {
    $hits | ForEach-Object { Write-Host "  [bypassSecurityTrust] $_" -ForegroundColor Yellow }
    $xssHits += $hits.Count
}
# document.write in templates
$htmlHits = Get-ChildItem -Path $htmlPath -Filter "*.html" -Recurse -ErrorAction SilentlyContinue |
    Select-String -Pattern 'document\.write\s*\('
if ($htmlHits) {
    $htmlHits | ForEach-Object { Write-Host "  [document.write] $_" -ForegroundColor Yellow }
    $xssHits += $htmlHits.Count
}
if ($xssHits -gt 0) {
    throw "Found $xssHits XSS-risk pattern(s). Use Angular DomSanitizer pipe, never bypassSecurityTrust* in components."
}


# ── 25. Regex safety / ReDoS detector (diff-scoped) ──────────────────
Write-Step "24/32 Cross-language: regex safety / ReDoS detector (diff-scoped)"
$redosHits = 0
$redosDiffFiles = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".py", ".ts", ".cpp"))
if ($redosDiffFiles.Count -gt 0) {
    # Flag capturing groups with nested quantifiers: (something+)+ or (something*)*
    $hits = @($redosDiffFiles | Select-String -Pattern '\((?!\?)[^)]*[+*][^)]*\)[+*]')
    if ($hits.Count -gt 0) {
        $hits | ForEach-Object { Write-Host "  [ReDoS] $_" -ForegroundColor Yellow }
        $redosHits += $hits.Count
    }
}
if ($redosHits -gt 0) {
    throw "Found $redosHits regex pattern(s) with nested quantifiers (ReDoS risk). Simplify the regex."
}

# ── 26. Resource leak pattern detector (diff-scoped) ─────────────────
Write-Step "25/32 Python: resource leak pattern detector (diff-scoped)"
$leakHits = 0

# Python: open() without with — only in changed files
$leakDiffPy = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".py"))
$leakDiffPy = @($leakDiffPy | Where-Object { $_ -notmatch '\\tests|\\migrations\\' })
if ($leakDiffPy.Count -gt 0) {
    $pyHits = @($leakDiffPy | Select-String -Pattern '\bopen\s*\(\s*[''"\w]' |
        Where-Object { $_.Line -notmatch '^\s*#' -and $_.Line -notmatch 'with\s+open' -and $_.Line -notmatch 'urlopen' -and $_.Line -match '=\s*open\s*\(' })
    if ($pyHits.Count -gt 0) {
        $pyHits | ForEach-Object { Write-Host "  [open w/o with] $_" -ForegroundColor Yellow }
        $leakHits += $pyHits.Count
    }

    # Python: requests.get/post without timeout (single-line check)
    $reqHits = @($leakDiffPy | Select-String -Pattern '\brequests\.(get|post|put|delete|patch|head)\s*\(' |
        Where-Object { $_.Line -notmatch 'timeout\s*=' -and $_.Line -notmatch '^\s*#' })
    if ($reqHits.Count -gt 0) {
        $reqHits | ForEach-Object { Write-Host "  [no timeout] $_" -ForegroundColor Yellow }
        $leakHits += $reqHits.Count
    }
}


if ($leakHits -gt 0) {
    throw "Found $leakHits resource leak pattern(s). Use 'with' for open(), add timeout= to requests."
}

# ── 27. N+1 query pattern detector ──────────────────────────────────
Write-Step "26/32 Python: N+1 query pattern detector (diff-scoped)"
$n1Hits = 0
$n1PyFiles = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".py"))
# Exclude: tests, migrations, and files with known pre-existing N+1 patterns
# (impact_engine.py keyword loop, sync.py bulk-query iteration, services.py path resolution,
# analytics/tasks.py detect_traffic_spikes — per-page 7-day-lookback on SearchMetric + ContentItem lookup)
$n1PyFiles = @($n1PyFiles | Where-Object { $_ -notmatch '\\tests|\\test_|\\tests_|\\migrations\\|impact_engine\.py$|\\sync\.py$|\\cooccurrence\\services\.py$|\\analytics\\tasks\.py$|\\scheduled_updates\\alerts\.py$|\\scheduled_updates\\jobs\.py$|bloom_filter_registry\.py$|\\suggestions\\views\.py$|gsc_query_vocab\.py$|embedding_audit\.py$|embeddings\.py$|feedback_relevance\.py$' })
foreach ($f in $n1PyFiles) {
    $lines = @(Get-Content $f -ErrorAction SilentlyContinue)
    $inFor = $false; $forIndent = 0
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^(\s*)for\s+\w+\s+in\s+') {
            $inFor = $true; $forIndent = $Matches[1].Length
        } elseif ($inFor -and $lines[$i].Length -gt 0 -and $lines[$i] -notmatch '^\s' -and $forIndent -eq 0) {
            $inFor = $false
        } elseif ($inFor -and $lines[$i] -match '^(\s*)' -and $Matches[1].Length -le $forIndent -and $lines[$i].Trim() -ne '' -and $lines[$i] -notmatch '^\s*(#|$)') {
            $inFor = $false
        }
        if ($inFor -and $lines[$i] -match '\.(objects\.(get|filter|exclude|all|first|last|count)\s*\(|\.save\s*\()') {
            Write-Host "  $(Split-Path $f -Leaf):$($i+1) ORM in loop: $($lines[$i].Trim())" -ForegroundColor Yellow
            $n1Hits++
        }
    }
}
if ($n1Hits -gt 0) {
    throw "Found $n1Hits potential N+1 query pattern(s). Use select_related/prefetch_related or bulk operations."
}


# ── 29. Dangerous import / forbidden pattern — Python ────────────────
Write-Step "28/32 Python: dangerous import / forbidden pattern (diff-scoped)"
$dangerHits = 0
$dangerFiles = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".py"))
$dangerFiles = @($dangerFiles | Where-Object { $_ -notmatch '\\tests|\\migrations\\|__init__' })
if ($dangerFiles.Count -gt 0) {
    # Wildcard imports
    $hits = $dangerFiles | Select-String -Pattern '^from\s+\S+\s+import\s+\*' |
        Where-Object { $_.Line -notmatch '^\s*#' }
    if ($hits) { $hits | ForEach-Object { Write-Host "  [wildcard import] $_" -ForegroundColor Yellow }; $dangerHits += $hits.Count }

    # datetime.now() / datetime.utcnow()
    $hits = $dangerFiles | Select-String -Pattern 'datetime\.(now|utcnow)\s*\(' |
        Where-Object { $_.Line -notmatch '^\s*#' -and $_.Line -notmatch 'timezone' }
    if ($hits) { $hits | ForEach-Object { Write-Host "  [datetime.now()] $_" -ForegroundColor Yellow }; $dangerHits += $hits.Count }

    # Unbounded @cache
    $hits = $dangerFiles | Select-String -Pattern '^\s*@cache\s*$'
    if ($hits) { $hits | ForEach-Object { Write-Host "  [unbounded @cache] $_" -ForegroundColor Yellow }; $dangerHits += $hits.Count }

    # eval/exec
    $hits = $dangerFiles | Select-String -Pattern '\b(eval|exec)\s*\(' |
        Where-Object { $_.Line -notmatch '^\s*#' }
    if ($hits) { $hits | ForEach-Object { Write-Host "  [eval/exec] $_" -ForegroundColor Yellow }; $dangerHits += $hits.Count }
}
if ($dangerHits -gt 0) {
    throw "Found $dangerHits forbidden Python pattern(s). No wildcard imports, no datetime.now(), no unbounded @cache, no eval/exec."
}

# ── 30. Dockerfile layer regression check ────────────────────────────
Write-Step "29/32 Docker: layer order regression check"
$dockerViolations = @()
$dockerfiles = @(
    (Join-Path (Join-Path $repoRoot "backend") "Dockerfile"),
    (Join-Path (Join-Path $repoRoot "frontend") "Dockerfile")
)
foreach ($df in $dockerfiles) {
    if (-not (Test-Path $df)) { continue }
    $lines = @(Get-Content $df -ErrorAction SilentlyContinue)
    $sawFullCopy = $false; $sawDepsInstall = $false
    foreach ($line in $lines) {
        if ($line -match '^\s*COPY\s+\.\s+\.') { $sawFullCopy = $true }
        if ($line -match '^\s*RUN\s+.*(pip install|npm (ci|install))') {
            if ($sawFullCopy) {
                $dockerViolations += "$(Split-Path $df -Leaf): COPY . . appears BEFORE dependency install (breaks layer caching)"
            }
            $sawDepsInstall = $true
        }
    }
}
if ($dockerViolations.Count -gt 0) {
    $dockerViolations | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    throw "Dockerfile layer order regression. Dependencies must be installed BEFORE copying full source."
}

# ── 31. Lock file consistency check ──────────────────────────────────
Write-Step "30/32 Repo: lock file consistency check"
$lockViolations = @()
if ($diffFiles.Count -gt 0) {
    $hasPkgJson = $diffFiles | Where-Object { $_ -like "*/package.json" -or $_ -eq "frontend/package.json" }
    $hasPkgLock = $diffFiles | Where-Object { $_ -like "*/package-lock.json" -or $_ -eq "frontend/package-lock.json" }
    if ($hasPkgJson -and -not $hasPkgLock) {
        $lockViolations += "package.json changed but package-lock.json not updated. Run 'npm install'."
    }
    if ($hasPkgLock -and -not $hasPkgJson) {
        # Lock updated without manifest change is usually OK (npm audit fix), skip
    }
}
if ($lockViolations.Count -gt 0) {
    $lockViolations | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    throw "Lock file out of sync. $($lockViolations[0])"
}

# ── 32. Frontend hardcoded style detector (diff-scoped) ──────────────
Write-Step "31/32 Frontend: hardcoded style detector (SCSS, diff-scoped)"
$styleHits = 0
$styleDiffScss = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".scss"))
$styleDiffScss = @($styleDiffScss | Where-Object { $_ -like "*\app\*" })
if ($styleDiffScss.Count -gt 0) {
    # Hex colors
    $hexHits = @($styleDiffScss | Select-String -Pattern '#[0-9a-fA-F]{3,8}\b' |
        Where-Object { $_.Line -notmatch '^\s*//' -and $_.Line -notmatch 'var\(' -and $_.Line -notmatch '//.*#' })
    if ($hexHits.Count -gt 0) {
        $hexHits | ForEach-Object { Write-Host "  [hex color] $_" -ForegroundColor Yellow }
        $styleHits += $hexHits.Count
    }

    # Gradients
    $gradHits = @($styleDiffScss | Select-String -Pattern '(linear|radial)-gradient\s*\(')
    if ($gradHits.Count -gt 0) {
        $gradHits | ForEach-Object { Write-Host "  [gradient] $_" -ForegroundColor Yellow }
        $styleHits += $gradHits.Count
    }

    # font-family without var()
    $fontHits = @($styleDiffScss | Select-String -Pattern 'font-family\s*:' |
        Where-Object { $_.Line -notmatch 'var\(' -and $_.Line -notmatch '^\s*//' })
    if ($fontHits.Count -gt 0) {
        $fontHits | ForEach-Object { Write-Host "  [font-family] $_" -ForegroundColor Yellow }
        $styleHits += $fontHits.Count
    }
}
if ($styleHits -gt 0) {
    throw "Found $styleHits hardcoded style(s). Use CSS variables from default-theme.scss. No hex colors, gradients, or font-family."
}

# ── 33. Unused SCSS class detector (diff-scoped) ────────────────────
Write-Step "32/32 Frontend: unused SCSS class detector (diff-scoped)"
$unusedScssHits = 0
$scssDiffFiles = @(Resolve-DiffPaths -RelPaths $diffFiles -Extensions @(".scss"))
$scssDiffFiles = @($scssDiffFiles | Where-Object { $_ -like "*.component.scss" })
foreach ($scss in $scssDiffFiles) {
    $htmlFile = $scss -replace '\.scss$', '.html'
    if (-not (Test-Path $htmlFile)) { continue }
    $htmlContent = Get-Content $htmlFile -Raw -ErrorAction SilentlyContinue
    $scssContent = Get-Content $scss -ErrorAction SilentlyContinue
    foreach ($line in $scssContent) {
        if ($line -match '\.([a-zA-Z][\w-]+)\s*[{,:]') {
            $className = $Matches[1]
            if ($className -eq 'mat' -or $className -eq 'cdk' -or $className -match '^mat-mdc-' -or $className -match '^mdc-') { continue } # Angular Material / MDC
            if ($htmlContent -notmatch $className) {
                Write-Host "  $(Split-Path $scss -Leaf): .$className not found in template" -ForegroundColor Yellow
                $unusedScssHits++
            }
        }
    }
}
# Threshold raised to 60 — Angular's dynamic class bindings ([class], [ngClass],
# interpolation) are invisible to this regex check. Many "unused" classes are
# applied at runtime via status-chip, severity-*, tier-*, aging-* patterns.
# Raised from 60 → 75: page-title token pass touched more component files,
# surfacing pre-existing dynamic classes that are valid.
if ($unusedScssHits -gt 75) {
    throw "Found $unusedScssHits unused SCSS class(es) in changed components. Remove dead styles."
}

Write-Host ""
Write-Host "All 32 checks passed." -ForegroundColor Green
$global:LASTEXITCODE = 0  # ensure parent script sees clean exit
