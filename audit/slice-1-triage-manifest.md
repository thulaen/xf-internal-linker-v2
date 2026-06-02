.env.example -> A -> commit
.githooks/_hook_helpers.py -> H -> revert
.githooks/check-code-review-lessons.py -> H -> revert
.githooks/check-lessons-read-at-session-start.py -> H -> revert
.githooks/check-no-rwx.py -> B -> commit
.githooks/check-paper-trail-evidence.py -> H -> revert
.githooks/check-paper-trail-read.py -> H -> revert
.githooks/check-registry-read.py -> H -> revert
.githooks/check-snapshotd-ritual.py -> H -> revert
.githooks/check-tdd-preflight.py -> H -> revert
.githooks/check-tdd-strict.py -> H -> revert
.githooks/check-test-case-mandate.py -> H -> revert
.githooks/test__hook_helpers.py -> H -> revert
.githooks/test_check_code_review_lessons.py -> H -> revert
.githooks/test_check_lessons_read_at_session_start.py -> H -> revert
.githooks/test_check_no_rwx.py -> B -> commit
.githooks/test_check_paper_trail_evidence.py -> H -> revert
.githooks/test_check_paper_trail_read.py -> H -> revert
.githooks/test_check_registry_read.py -> H -> revert
.githooks/test_check_snapshotd_ritual.py -> H -> revert
.githooks/test_check_tdd_preflight.py -> H -> revert
.githooks/test_check_tdd_strict.py -> H -> revert
.githooks/test_check_test_case_mandate.py -> H -> revert
.githooks/test_hook_messages.py -> H -> revert
.gitignore -> B -> commit
AGENT-HANDOFF.md -> G -> commit
AGENTS.md -> G -> commit
AI-CODING-GUIDELINES.md -> H -> revert
AI-CONTEXT.md -> H -> revert
CLAUDE.md -> G -> commit
CODEX.md -> G -> commit
COMPILED-LANGUAGE-RULES.md -> H -> revert
GEMINI.md -> G -> commit
PLAIN-ENGLISH-RULE.md -> G -> commit
audit/README.md -> H -> revert
audit/commit_failures_lookup_log.jsonl -> H -> revert
audit/resolved_issues_lookup_log.jsonl -> H -> revert
backend/Dockerfile -> H -> revert
backend/apps/api/urls.py -> H -> revert
backend/apps/audit/tasks.py -> H -> revert
backend/apps/audit/tests_glitchtip_compose_integrity.py -> H -> revert
backend/apps/audit/tests_tasks_helpers.py -> H -> revert
backend/apps/audit/tests_tool_compose_integrity.py -> H -> revert
backend/apps/auto_issues/apps.py -> H -> revert
backend/apps/auto_issues/management/commands/decision_point.py -> H -> revert
backend/apps/auto_issues/management/commands/file_gh_helper_autoissue.py -> H -> revert
backend/apps/auto_issues/management/commands/file_mutation_survivors.py -> H -> revert
backend/apps/auto_issues/management/commands/file_task_issues.py -> H -> revert
backend/apps/auto_issues/management/commands/inspect_profiles.py -> H -> revert
backend/apps/auto_issues/management/commands/log_code_review_lessons.py -> H -> revert
backend/apps/auto_issues/management/commands/log_tdd_lesson.py -> H -> revert
backend/apps/auto_issues/management/commands/log_test_case.py -> H -> revert
backend/apps/auto_issues/management/commands/print_open_issues.py -> H -> revert
backend/apps/auto_issues/management/commands/print_open_snapshots.py -> H -> revert
backend/apps/auto_issues/management/commands/report_hook_false_positive.py -> H -> revert
backend/apps/auto_issues/management/commands/verify_autoissue_quota.py -> H -> revert
backend/apps/auto_issues/models.py -> H -> revert
backend/apps/auto_issues/services/categories.py -> H -> revert
backend/apps/auto_issues/services/ci_failed_runs.py -> H -> revert
backend/apps/auto_issues/services/dedup.py -> H -> revert
backend/apps/auto_issues/services/faro_picker.py -> H -> revert
backend/apps/auto_issues/services/glitchtip_picker.py -> H -> revert
backend/apps/auto_issues/services/internal_picker.py -> H -> revert
backend/apps/auto_issues/services/loki_picker.py -> H -> revert
backend/apps/auto_issues/services/multi_lang_picker.py -> H -> revert
backend/apps/auto_issues/services/pyroscope_picker.py -> H -> commit
backend/apps/auto_issues/services/resolved_issue_index.py -> H -> revert
backend/apps/auto_issues/services/scoring.py -> H -> revert
backend/apps/auto_issues/services/slow_query_picker.py -> H -> revert
backend/apps/auto_issues/services/tempo_picker.py -> H -> revert
backend/apps/auto_issues/tasks.py -> H -> revert
backend/apps/auto_issues/tests/test_decision_point.py -> H -> revert
backend/apps/auto_issues/tests/test_file_gh_helper_autoissue.py -> H -> revert
backend/apps/auto_issues/tests/test_file_mutation_survivors.py -> H -> revert
backend/apps/auto_issues/tests/test_file_task_issues.py -> H -> revert
backend/apps/auto_issues/tests/test_log_code_review_lessons.py -> H -> revert
backend/apps/auto_issues/tests/test_log_test_case.py -> H -> revert
backend/apps/auto_issues/tests/test_multi_lang_picker.py -> H -> revert
backend/apps/auto_issues/tests/test_preflight_tdd.py -> H -> revert
backend/apps/auto_issues/tests_ci_failed_runs.py -> H -> revert
backend/apps/auto_issues/tests_dedup.py -> H -> revert
backend/apps/auto_issues/tests_faro_picker.py -> H -> revert
backend/apps/auto_issues/tests_inspect_profiles_command.py -> H -> revert
backend/apps/auto_issues/tests_pickers.py -> H -> revert
backend/apps/auto_issues/tests_print_open_issues_command.py -> H -> revert
backend/apps/auto_issues/tests_print_open_snapshots_command.py -> H -> revert
backend/apps/auto_issues/tests_report_hook_false_positive.py -> H -> revert
backend/apps/auto_issues/tests_verify_autoissue_quota.py -> H -> revert
backend/apps/auto_issues/tests_views.py -> H -> revert
backend/apps/auto_issues/urls.py -> H -> revert
backend/apps/auto_issues/views.py -> H -> revert
backend/apps/core/apps.py -> H -> revert
backend/apps/core/backups.py -> H -> revert
backend/apps/core/management/commands/backup_db_now.py -> H -> revert
backend/apps/core/tasks_backups.py -> H -> revert
backend/apps/core/tests_compiled_artifacts.py -> H -> revert
backend/apps/core/tests_dependency_security_pins.py -> H -> revert
backend/apps/core/tests_settings_helpers.py -> H -> revert
backend/apps/health/services.py -> H -> revert
backend/apps/health/tasks.py -> H -> revert
backend/apps/health/tests.py -> H -> revert
backend/apps/observability/management/commands/check_observability_health.py -> A -> commit
backend/apps/paper_trail/management/commands/defer_work.py -> H -> revert
backend/apps/paper_trail/management/commands/migrate_handoff_deferrals.py -> H -> revert
backend/apps/paper_trail/management/commands/verify_paper_trail_quota.py -> H -> revert
backend/apps/paper_trail/management/commands/verify_rewrite_exemption.py -> H -> revert
backend/apps/paper_trail/models.py -> H -> revert
backend/apps/paper_trail/tests_migrate_handoff_command.py -> H -> revert
backend/apps/pipeline/services/async_http.py -> H -> revert
backend/apps/pipeline/services/faiss_index.py -> H -> revert
backend/apps/pipeline/services/rare_term_propagation.py -> H -> revert
backend/apps/pipeline/services/sentence_splitter.py -> H -> revert
backend/apps/pipeline/services/slate_diversity.py -> H -> revert
backend/apps/pipeline/services/test_async_http.py -> H -> revert
backend/apps/pipeline/services/text_cleaner.py -> H -> revert
backend/apps/pipeline/services/trustrank_auto_seeder.py -> H -> revert
backend/apps/pipeline/services/weighted_pagerank.py -> H -> revert
backend/apps/pipeline/tasks_broken_links.py -> H -> revert
backend/apps/pipeline/tasks_embedding_bakeoff.py -> H -> revert
backend/apps/pipeline/tasks_tuning.py -> H -> revert
backend/apps/pipeline/tests_tuning_tasks.py -> H -> revert
backend/apps/realtime/services.py -> H -> revert
backend/apps/scheduled_updates/jobs.py -> H -> revert
backend/apps/sources/entity_salience.py -> H -> revert
backend/apps/sources/fasttext_langid.py -> H -> revert
backend/apps/sources/passages.py -> H -> revert
backend/apps/sources/url_canonical.py -> H -> revert
backend/apps/suggestions/meta_registry.py -> H -> revert
backend/apps/suggestions/migrations/0001_initial.py -> H -> revert
backend/apps/suggestions/migrations/0002_rename_diag_run_reason_idx_suggestions_pipelin_a2cf09_idx_and_more.py -> H -> revert
backend/apps/suggestions/migrations/0017_refresh_recommended_feature_flags.py -> H -> revert
backend/apps/suggestions/migrations/0068_suggestion_unique_5tuple.py -> H -> revert
backend/apps/suggestions/models.py -> H -> revert
backend/apps/suggestions/readiness.py -> H -> revert
backend/apps/suggestions/services/weight_tuner.py -> H -> revert
backend/apps/suggestions/tests.py -> H -> revert
backend/apps/suggestions/tests_weight_tuner.py -> H -> revert
backend/apps/suggestions/tunable_registry.py -> H -> revert
backend/apps/sync/services/webhooks.py -> H -> revert
backend/apps/sync/views.py -> H -> revert
backend/apps/training/loss/lambda_loss.py -> H -> revert
backend/config/catchup.py -> H -> revert
backend/config/settings/base.py -> H -> revert
backend/config/settings/celery_schedules.py -> H -> revert
backend/config/settings/ci.py -> H -> revert
backend/config/settings/development.py -> H -> revert
backend/config/urls.py -> H -> revert
backend/conftest.py -> H -> revert
backend/extensions/fuzz/CMakeLists.txt -> H -> revert
backend/extensions/scoring.cpp -> H -> revert
backend/mcp_server.py -> H -> revert
backend/pytest.ini -> H -> revert
backend/requirements.txt -> H -> revert
config/docker-build-routing.json -> H -> revert
config/observability-services.json -> H -> revert
docker-compose.yml -> H -> revert
docs/CI-GATES.md -> H -> revert
docs/CODE-COVERAGE-RULES.md -> H -> revert
docs/DOCKER-BUILDKIT-S3-SETUP.md -> B -> commit
docs/MUTATION-TESTING.md -> H -> revert
docs/PAPER-TRAIL-EVIDENCE-RULE.md -> H -> revert
docs/PAPER-TRAIL.md -> H -> revert
docs/SCCACHE-S3-SETUP.md -> B -> commit
docs/TESTING.md -> H -> revert
docs/reports/REPORT-REGISTRY.md -> H -> revert
docs/specs/fr-rwx-teardown.md -> B -> commit
docs/specs/fr-sidecars-host.md -> I -> commit
docs/specs/fr-smart-docker-build-routing.md -> I -> commit
docs/specs/opentelemetry-profiles-pyroscope.md -> I -> commit
frontend/angular.json -> H -> revert
frontend/eslint.config.js -> H -> revert
frontend/package-lock.json -> H -> revert
frontend/package.json -> H -> revert
frontend/src/app/app.component.scss -> H -> revert
frontend/src/app/app.component.ts -> H -> revert
frontend/src/app/app.config.ts -> H -> revert
frontend/src/app/app.routes.ts -> H -> revert
frontend/src/app/core/directives/tab-fragment-router.directive.spec.ts -> H -> revert
frontend/src/app/core/directives/tab-fragment-router.directive.ts -> H -> revert
frontend/src/app/core/routing/deep-link-catalog.spec.ts -> H -> revert
frontend/src/app/core/routing/deep-link-catalog.ts -> H -> revert
frontend/src/app/core/services/auto-issues.service.ts -> H -> revert
frontend/src/app/core/services/paste-uuid-navigator.service.ts -> H -> revert
frontend/src/app/core/util/virtual-scroll-datasource.ts -> H -> revert
frontend/src/app/core/utils/scroll-highlight.utils.ts -> H -> revert
frontend/src/app/core/workers/parse.worker.ts -> H -> revert
frontend/src/app/dashboard/command-suggestions/command-suggestions.component.ts -> H -> revert
frontend/src/app/dashboard/trend-deltas/trend-deltas.component.ts -> H -> revert
frontend/src/app/error-log/error-log.component.html -> H -> revert
frontend/src/app/error-log/error-log.component.scss -> H -> revert
frontend/src/app/error-log/error-log.component.spec.ts -> H -> revert
frontend/src/app/error-log/error-log.component.ts -> H -> revert
frontend/src/app/login/login.component.spec.ts -> D -> commit
frontend/src/app/login/login.component.ts -> D -> commit
frontend/src/app/mcp/mcp.component.html -> H -> revert
frontend/src/app/mcp/mcp.component.ts -> H -> revert
frontend/src/app/settings/settings-constants.ts -> H -> revert
frontend/src/app/shared/ui/glossary/glossary.data.ts -> A -> commit
frontend/src/environments/environment.production.ts -> H -> revert
frontend/src/environments/environment.ts -> H -> revert
frontend/src/main.ts -> H -> revert
frontend/src/styles.scss -> H -> revert
frontend/tests/a11y.spec.ts -> H -> revert
frontend/tests/capture/page-snapshot.spec.ts -> H -> revert
frontend/tests/dashboard-smoke.spec.ts -> H -> revert
grafana/provisioning/datasources/datasources.yaml -> H -> revert
nginx/Dockerfile -> H -> revert
otelcol-config.yaml -> H -> revert
scripts/_quality_concurrency.sh -> H -> revert
scripts/check_quality_policy.py -> H -> revert
scripts/commit_scope.py -> H -> revert
scripts/cpp_mutation_targets.py -> H -> revert
scripts/destructive_command_guard.py -> C -> commit
scripts/detect_changed_modules.py -> H -> revert
scripts/lookup_disk_index.py -> H -> revert
scripts/precommit-docker.sh -> H -> revert
scripts/prepush-docker.sh -> H -> revert
scripts/reset-docker-sockets.ps1 -> H -> revert
scripts/run-angular-quality.sh -> H -> revert
scripts/run-buf-lint.sh -> H -> revert
scripts/run-cpp-benchmarks.sh -> H -> revert
scripts/run-cpp-coverage.sh -> H -> revert
scripts/run-cpp-edge-tests.sh -> H -> revert
scripts/run-cpp-fuzz-smoke.sh -> H -> revert
scripts/run-cpp-infer.sh -> H -> revert
scripts/run-cpp-mutation.sh -> H -> revert
scripts/run-cpp-quality.sh -> H -> revert
scripts/run-cpp-sanitizers.sh -> H -> revert
scripts/run-cpp-static.sh -> H -> revert
scripts/run-cpp-tests.sh -> H -> revert
scripts/run-go-bench.sh -> H -> revert
scripts/run-go-format.sh -> H -> revert
scripts/run-go-gosec.sh -> H -> revert
scripts/run-go-lint.sh -> H -> revert
scripts/run-go-mutation.sh -> H -> revert
scripts/run-go-quality.sh -> H -> revert
scripts/run-go-staticcheck.sh -> H -> revert
scripts/run-go-tests.sh -> H -> revert
scripts/run-go-vet.sh -> H -> revert
scripts/run-python-quality.sh -> H -> revert
scripts/run_quality_step.py -> H -> revert
scripts/select_python_test_targets.py -> H -> revert
scripts/set-aws-creds.ps1 -> B -> commit
scripts/smart_build.py -> H -> revert
scripts/tdd_write_guard.py -> C -> commit
scripts/test_commit_scope.py -> H -> revert
scripts/test_cpp_mutation_targets.py -> H -> revert
scripts/test_detect_changed_modules.py -> H -> revert
scripts/test_lookup_disk_index.py -> H -> revert
scripts/test_precommit_docker.py -> H -> revert
scripts/test_select_python_test_targets.py -> H -> revert
scripts/test_smart_build.py -> H -> revert
scripts/test_tdd_write_guard.py -> C -> commit
services/streamd/cmd/streamd/main.go -> E -> defer
tools/mutation/Dockerfile -> H -> revert
.bundle-size-baseline.json -> H -> revert
.codebuild/ -> B -> commit
.codex/ -> H -> revert
.gitattributes -> H -> revert
.githooks/check-agent-rules-sync.py -> H -> revert
.githooks/check-autoissue-quota.py -> H -> revert
.githooks/check-c-abi-conformance.py -> H -> revert
.githooks/check-gh-actions-read.py -> H -> revert
.githooks/check-lua-sandbox.py -> H -> revert
.githooks/check-lua-test-isolation.py -> H -> revert
.githooks/check-lua-test-sandbox.py -> H -> revert
.githooks/check-luajit-dialect.py -> H -> revert
.githooks/check-native-observability-wired.py -> H -> revert
.githooks/check-no-destructive-docker-commands.py -> H -> revert
.githooks/check-rust-mandate.py -> H -> revert
.githooks/check_rust_mandate.py -> H -> revert
.githooks/findings-transcript.sh -> H -> revert
.githooks/lua/ -> H -> revert
.githooks/prepare-commit-msg -> H -> revert
.githooks/test_check_agent_rules_sync.py -> H -> revert
.githooks/test_check_autoissue_quota.py -> H -> revert
.githooks/test_check_c_abi_conformance.py -> H -> revert
.githooks/test_check_gh_actions_read.py -> H -> revert
.githooks/test_check_native_observability_wired.py -> H -> revert
.githooks/test_check_no_destructive_docker_commands.py -> H -> revert
.githooks/test_check_rust_mandate.py -> H -> revert
.githooks/test_plain_english_rule.py -> H -> revert
.githooks/test_prepare_commit_msg.py -> H -> revert
.github/workflows/ci-failure-to-autoissue.yml -> H -> revert
.github/workflows/scoped-mutation.yml -> H -> revert
.github/workflows/test_ci_failure_workflow.yml.test -> H -> revert
.luacheckrc -> H -> revert
.tmp/ -> H -> revert
.tool-versions -> H -> revert
apps/ -> H -> revert
audit/findings_buffer.jsonl -> H -> revert
audit/github_actions_failures.jsonl -> H -> revert
audit/helper_failures.jsonl -> H -> revert
audit/scope_decisions.jsonl -> H -> revert
audit/sticky_reads.jsonl -> H -> revert
backend/apps/audit/tests_compose_gpu_discipline.py -> H -> revert
backend/apps/audit/tests_frontend_dev_compose.py -> H -> revert
backend/apps/audit/tests_gpu_runtime_visibility.py -> H -> revert
backend/apps/audit/tests_gpu_usage_per_service.py -> H -> revert
backend/apps/auto_issues/_sidecars/ -> H -> revert
backend/apps/auto_issues/concept_tags.py -> H -> revert
backend/apps/auto_issues/findbugs_views.py -> H -> revert
backend/apps/auto_issues/management/commands/check_docker_health.py -> H -> revert
backend/apps/auto_issues/management/commands/debug_autoissue.py -> H -> revert
backend/apps/auto_issues/management/commands/drain_findings_buffer.py -> H -> revert
backend/apps/auto_issues/management/commands/file_ci_failure.py -> H -> revert
backend/apps/auto_issues/management/commands/file_hook_finding.py -> H -> revert
backend/apps/auto_issues/management/commands/import_rust_findings.py -> H -> revert
backend/apps/auto_issues/management/commands/ingest_sonarqube_issues.py -> H -> revert
backend/apps/auto_issues/management/commands/print_failed_github_actions.py -> H -> revert
backend/apps/auto_issues/management/commands/rotate_gh_actions_log.py -> H -> revert
backend/apps/auto_issues/management/commands/rotate_scope_log.py -> H -> revert
backend/apps/auto_issues/management/commands/verify_chain_batch.py -> H -> revert
backend/apps/auto_issues/migrations/0014_add_sonarqube_source.py -> H -> revert
backend/apps/auto_issues/migrations/0015_seed_rust_defect_categories.py -> J -> commit
backend/apps/auto_issues/migrations/0016_alter_autoissue_source.py -> H -> revert
backend/apps/auto_issues/migrations/0017_findbugs_learned_lesson.py -> H -> revert
backend/apps/auto_issues/reproduce_issue_522.py -> H -> revert
backend/apps/auto_issues/services/chain_batch.py -> H -> revert
backend/apps/auto_issues/services/docker_health.py -> H -> revert
backend/apps/auto_issues/services/findbugs.py -> H -> revert
backend/apps/auto_issues/services/gh_actions_history.py -> H -> revert
backend/apps/auto_issues/services/lighthouse_picker.py -> H -> revert
backend/apps/auto_issues/services/rust_findings.py -> H -> revert
backend/apps/auto_issues/services/session_boundary.py -> H -> revert
backend/apps/auto_issues/services/sonarqube.py -> H -> revert
backend/apps/auto_issues/services/vmalert_picker.py -> H -> revert
backend/apps/auto_issues/sidecar_views.py -> H -> revert
backend/apps/auto_issues/signals.py -> H -> revert
backend/apps/auto_issues/tests/test_chain_batch_service.py -> H -> revert
backend/apps/auto_issues/tests/test_drain_findings_buffer.py -> H -> revert
backend/apps/auto_issues/tests/test_file_ci_failure.py -> H -> revert
backend/apps/auto_issues/tests/test_lighthouse_pg_stat_picker.py -> H -> revert
backend/apps/auto_issues/tests/test_print_failed_github_actions.py -> H -> revert
backend/apps/auto_issues/tests/test_rotate_gh_actions_log.py -> H -> revert
backend/apps/auto_issues/tests/test_scope_cap_autoissue.py -> H -> revert
backend/apps/auto_issues/tests/test_sidecar_clients.py -> H -> revert
backend/apps/auto_issues/tests/test_verify_autoissue_quota_hard.py -> H -> revert
backend/apps/auto_issues/tests/test_verify_chain_batch.py -> H -> revert
backend/apps/auto_issues/tests/test_verify_paper_trail_quota_hard.py -> H -> revert
backend/apps/auto_issues/tests_debug_autoissue.py -> H -> revert
backend/apps/auto_issues/tests_docker_compose_sonar_services.py -> H -> revert
backend/apps/auto_issues/tests_docker_health.py -> H -> revert
backend/apps/auto_issues/tests_findbugs_operational.py -> H -> revert
backend/apps/auto_issues/tests_import_rust_findings.py -> H -> revert
backend/apps/auto_issues/tests_ingest_sonarqube_findings_task.py -> H -> revert
backend/apps/auto_issues/tests_registry_refresh.py -> H -> revert
backend/apps/auto_issues/tests_sonar_autoscan_runtime.py -> H -> commit
backend/apps/auto_issues/tests_sonarqube_direct_findings.py -> H -> revert
backend/apps/auto_issues/tests_sonarqube_import.py -> H -> revert
backend/apps/auto_issues/tests_vmalert_picker.py -> H -> revert
backend/apps/core/management/commands/allow_data_op.py -> H -> revert
backend/apps/core/management/commands/ensure_admin.py -> H -> revert
backend/apps/core/tests_allow_data_op.py -> H -> revert
backend/apps/core/tests_backups.py -> H -> revert
backend/apps/core/tests_data_protection_triggers.py -> H -> revert
backend/apps/core/tests_ensure_admin.py -> H -> revert
backend/apps/diagnostics/_sidecars/ -> F -> defer
backend/apps/diagnostics/test_sidecar_clients.py -> F -> defer
backend/apps/observability/__init__.py -> A -> commit
backend/apps/observability/api.py -> A -> commit
backend/apps/observability/apps.py -> A -> commit
backend/apps/observability/helpers.py -> A -> commit
backend/apps/observability/instruments.py -> A -> commit
backend/apps/observability/metric_specs.py -> A -> commit
backend/apps/observability/migrations/ -> A -> commit
backend/apps/observability/models.py -> A -> commit
backend/apps/observability/services/ -> A -> commit
backend/apps/observability/tasks.py -> A -> commit
backend/apps/observability/tests_alert_rules.py -> A -> commit
backend/apps/observability/tests_faro_alloy_smoke.py -> A -> commit
backend/apps/observability/tests_gap_detector.py -> A -> commit
backend/apps/observability/tests_metrics_endpoint.py -> A -> commit
backend/apps/observability/tests_reserved_instruments.py -> A -> commit
backend/apps/observability/tests_stack_foundation.py -> A -> commit
backend/apps/observability/tests_stack_view.py -> A -> commit
backend/apps/observability/urls.py -> A -> commit
backend/apps/observability/views.py -> A -> commit
backend/apps/ops_feed/_sidecars/ -> F -> defer
backend/apps/ops_feed/tasks.py -> F -> defer
backend/apps/ops_feed/test_sidecar_clients.py -> F -> defer
backend/apps/paper_trail/management/commands/debug_paper_trail.py -> H -> revert
backend/apps/paper_trail/migrations/0006_alter_papertrailentry_abstract_and_status.py -> H -> revert
backend/apps/paper_trail/tests_debug_paper_trail.py -> H -> revert
backend/apps/paper_trail/tests_migrations.py -> H -> revert
backend/apps/pipeline/services/gpu_idle_release.py -> H -> revert
backend/apps/pipeline/services/model_resource_profile.py -> H -> revert
backend/apps/pipeline/services/tests_gpu_idle_release.py -> H -> revert
backend/apps/pipeline/services/tests_model_resource_profile.py -> H -> revert
backend/apps/sources/_sidecars/ -> H -> revert
backend/apps/sources/test_sidecar_clients.py -> H -> revert
backend/apps/work_queue/ -> F -> defer
backend/audit/ -> H -> revert
backend/config/tests/test_pyroscope_sample_rate.py -> H -> commit
backend/debug_perfetto.py -> H -> revert
backend/extensions/fuzz/fuzz_lesson_index.cpp -> H -> revert
backend/extensions/fuzz/fuzz_papertrail_dedup.cpp -> H -> revert
backend/insert_pprof.py -> H -> revert
backend/scripts/commit_a_paper_trail_ceremony.py -> H -> revert
backend/scripts/commit_a_resolve_30_picks.py -> H -> revert
backend/scripts/log_commit_a_failures.py -> H -> revert
backend/test_pprof_all.py -> H -> revert
backend/tmp/ -> H -> revert
config/aws-cache-buckets.json -> H -> revert
config/vmagent/ -> H -> revert
config/vmalert/ -> H -> revert
coverage-modules.yaml -> H -> revert
docs/SLICE-01-WORKING-COPY-INVENTORY.md -> H -> revert
docs/agent-rules-sync-manifest.yml -> H -> revert
docs/architecture/ -> H -> revert
docs/development/ -> H -> revert
docs/operations/ -> H -> revert
docs/plans/ -> I -> commit
docs/specs/autoissue-quota-hard-block.md -> I -> commit
docs/specs/fr-agent-aware-correlation.md -> I -> commit
docs/specs/fr-agent-code-standards-middleware.md -> I -> commit
docs/specs/fr-agent-rules-sync.md -> I -> commit
docs/specs/fr-antigravity-cli-repo-setup.md -> I -> commit
docs/specs/fr-autoissue-native-retrieval.md -> I -> commit
docs/specs/fr-autoissue-vmalert-source.md -> I -> commit
docs/specs/fr-bounded-waits-timeout-sweep.md -> I -> commit
docs/specs/fr-c-abi-wrapper-standard.md -> I -> commit
docs/specs/fr-chain-batch-verifier.md -> I -> commit
docs/specs/fr-code-validation-engine.md -> I -> commit
docs/specs/fr-findbugs-llamacpp-smollm2.md -> I -> commit
docs/specs/fr-findbugs-observability.md -> I -> commit
docs/specs/fr-glitchtip-direct-findings.md -> I -> commit
docs/specs/fr-gpu-idle-release.md -> I -> commit
docs/specs/fr-gui-observability-page.md -> I -> commit
docs/specs/fr-hook-finding-autoissue.md -> I -> commit
docs/specs/fr-k8s-wsl2-networking.md -> I -> commit
docs/specs/fr-layered-data-loss-prevention.md -> I -> commit
docs/specs/fr-lua-testing-toolchain.md -> I -> commit
docs/specs/fr-mint-glitchtip-placement.md -> I -> commit
docs/specs/fr-mint-quality-tool-placement.md -> I -> commit
docs/specs/fr-multi-lang-observability-picker.md -> I -> commit
docs/specs/fr-no-silent-disablement.md -> I -> commit
docs/specs/fr-observability-vm-grafana.md -> I -> commit
docs/specs/fr-paper-trail-handoff-migration.md -> I -> commit
docs/specs/fr-proactive-ticketing-and-business-impact.md -> I -> commit
docs/specs/fr-prometheus-exposition.md -> I -> commit
docs/specs/fr-pyroscope-errors-d3-flamegraph.md -> I -> commit
docs/specs/fr-quality-scope-discipline.md -> I -> commit
docs/specs/fr-reserved-alerts.md -> I -> commit
docs/specs/fr-rust-speccheck.md -> I -> commit
docs/specs/fr-self-healing-agent-rollback.md -> I -> commit
docs/specs/fr-work-queue-agent-control.md -> I -> commit
findbugs-current.png -> Drop -> drop
findbugs-login.png -> Drop -> drop
findbugs-polished-fresh.png -> Drop -> drop
findbugs-polished.png -> Drop -> drop
frontend/Dockerfile.dev -> H -> revert
frontend/nginx-lua/ -> H -> revert
frontend/src/app/core/faro.module.spec.ts -> H -> revert
frontend/src/app/core/faro.module.ts -> H -> revert
frontend/src/app/dev/ -> F -> defer
frontend/src/app/error-log/sidecars-data.service.spec.ts -> H -> revert
frontend/src/app/error-log/sidecars-data.service.ts -> H -> revert
frontend/src/app/find-bugs/ -> F -> defer
frontend/src/app/observability/ -> A -> commit
frontend/src/app/shared/directives/pe-helper.directive.spec.ts -> H -> revert
frontend/src/app/shared/directives/pe-helper.directive.ts -> H -> revert
frontend/src/app/work-queue/ -> F -> defer
grafana/dashboards/xf-cleaning.json -> H -> revert
grafana/dashboards/xf-crawlers.json -> H -> revert
grafana/dashboards/xf-embeddings.json -> H -> revert
grafana/dashboards/xf-import.json -> H -> revert
grafana/dashboards/xf-indexing.json -> H -> revert
grafana/dashboards/xf-review.json -> H -> revert
grafana/dashboards/xf-scoring.json -> H -> revert
grafana/dashboards/xf-sentence-split.json -> H -> revert
grafana/dashboards/xf-suggestions.json -> H -> revert
grafana/dashboards/xf-system-health.json -> H -> revert
luacov.stats.out -> Drop -> drop
nginx/nginx.dev.conf -> H -> revert
pyroscope-ebpf.alloy -> H -> commit
reports/ -> H -> revert
rust-toolchain.toml -> H -> revert
scripts/_rules_sync_helpers.py -> H -> revert
scripts/apply-cache-retention.ps1 -> H -> revert
scripts/check-docker-health.ps1 -> H -> revert
scripts/check-mint-glitchtip.ps1 -> H -> commit
scripts/check-mint-quality-tools.ps1 -> H -> commit
scripts/check_lua_dialect.lua -> H -> revert
scripts/enumerate_failed_jobs.py -> H -> revert
scripts/install-lua-tools.sh -> H -> revert
scripts/lua_busted_helper.lua -> H -> revert
scripts/lua_ffi_smoke.lua -> H -> revert
scripts/mutation_policy.sh -> H -> revert
scripts/quality_cores.py -> H -> revert
scripts/quality_cores.sh -> H -> revert
scripts/run-haskell-quality.sh -> H -> revert
scripts/run-lua-pretooluse-advisor.py -> H -> revert
scripts/run-lua-quality.sh -> H -> revert
scripts/run-multi-lang-observability-picker.py -> H -> revert
scripts/run-parallel-mutation.sh -> H -> revert
scripts/run-python-repo-mutation.sh -> H -> revert
scripts/run-rust-quality.sh -> H -> revert
scripts/scope_cap.py -> H -> revert
scripts/start-antigravity.ps1 -> H -> revert
scripts/start-mint-glitchtip.ps1 -> H -> commit
scripts/start-mint-quality-tools.ps1 -> H -> commit
scripts/sync_agent_rules.py -> H -> revert
scripts/test_antigravity_cli_setup.py -> H -> revert
scripts/test_cache_retention_config.py -> H -> revert
scripts/test_compiled_language_agent_rules.py -> H -> revert
scripts/test_frontend_build_config.py -> H -> revert
scripts/test_lua_mutation_toolchain.py -> H -> revert
scripts/test_lua_mutator_cli.py -> H -> revert
scripts/test_lua_toolchain.py -> H -> revert
scripts/test_parallel_mutation_mint.py -> H -> commit
scripts/test_python_repo_mutation.py -> H -> revert
scripts/test_quality_cores.py -> H -> revert
scripts/test_reset-docker-sockets.ps1 -> H -> revert
scripts/test_run_quality_step.py -> H -> revert
scripts/test_scope_audit.py -> H -> revert
scripts/test_scope_cap.py -> H -> revert
scripts/test_session_lookup_speed.py -> H -> revert
scripts/triage_script.py -> H -> revert
services/findbugs-haskell/ -> H -> revert
services/sidecars/ -> H -> revert
services/speccheck/ -> H -> revert
services/streamd/cmd/streamd/main.go.tmp -> E -> drop
services/streamd/internal/qualitycores/ -> E -> defer
tests/ -> H -> revert
tmp/claude-handoff/ -> H -> revert
tmp/findbugs-agile-upgrade-bossy-prompt.md -> H -> revert
tmp/k8s01-docker-desktop-networking-paper-trail-draft.md -> H -> revert
tmp/lua-advisor-payload-12c2eac97e354c6ca4ed396029d84c3e.json -> H -> revert
tmp/lua-advisor-payload-1f5ddf56b06344b880475953ae4b52cc.json -> H -> revert
tmp/lua-advisor-payload-24dda7fb396a48169ebb6235226420a2.json -> H -> revert
tmp/lua-advisor-payload-3cccac1c0f5a4313bc09c36623175a38.json -> H -> revert
tmp/lua-advisor-payload-8e24deb210c5466e9f320ac155172bf9.json -> H -> revert
tmp/lua-advisor-payload-edf8faeb084b4f26841160dde4969278.json -> H -> revert
tmp/lua-advisor-payload-f80f1584e96946a8af6982d6c9ba1f22.json -> H -> revert
tmp/sentinel-merge-continuation-prompt.md -> H -> revert
tmp/sentinel-merge-kickoff-prompt.md -> H -> revert
tmp/unified-static-analysis-graph-ranking-research-prompt.md -> H -> revert
tools/lua/ -> H -> revert
tools/preflight/ -> H -> revert
xf-internal-linker-v2.code-workspace -> H -> revert


### Dry-run precommit hooks status
| Hook | Status | Output Snippet |
| --- | --- | --- |
| check-agent-rules-sync.py | PASS |  |
| check-autoissue-quota.py | TIMEOUT | Hung and was killed after 20s. |
| check-autotuner-registry.py | PASS |  |
| check-bundle-size.py | FAIL | Traceback (most recent call last): File "C:\Users\goldm\Dev\xf-internal-linker-v2\.githooks\check-bundle-size.py", line 130, in <module> |
| check-c-abi-conformance.py | FAIL | Exception in thread Thread-3 (_readerthread): Traceback (most recent call last): |
| check-code-review-lessons.py | FAIL | FAIL check-code-review-lessons: marker says only 12 file(s) reviewed but 220 production source file(s) are staged. WHY: Rule G requires every touched file to be accounted for in the review. The review must cover bugs, silent errors, correctness, tech debt, maintainability, duplication, and long functions. |
| check-commit-failures-lookup.py | FAIL | FAIL check-commit-failures-lookup: zero commit-failure lookups recorded for task_id=f4c61529-f5bf-4330-a8bb-b72af57456c3 in audit\commit_failures_lookup_log.jsonl. WHY: the 2026-05-18 user rule requires every agent to look up prior commit failures BEFORE committing, parallel to the per-file search_resolved_issues mandate. Without the lookup, the agent risks repeating a failure (timeout, orphan DB connection, missing marker, etc.) that an earlier session already diagnosed. A memory-only lookup does NOT satisfy the mandate; the audit log is the disk-backed evidence. |
| check-coverage-erosion.py | TIMEOUT | Hung and was killed after 20s. |
| check-cpp-lifecycle.py | PASS |  |
| check-debug-code.py | PASS |  |
| check-decision-point.py | PASS |  |
| check-default-on-rule.py | PASS |  |
| check-deferral-filed.py | PASS |  |
| check-design-patterns.py | PASS |  |
| check-django-deploy.py | PASS |  |
| check-file-size.py | FAIL | FAIL check-file-size: file(s) over the 1,500-line cap from CLAUDE.md. backend/apps/health/services.py: 2339 lines — over the 1500-line cap from CLAUDE.md. Split into named modules. If this file is being actively decomposed, add the path to .githooks/file-size-grandfather.txt with the current line count and remove it once the split lands. |
| check-fk-on-delete.py | PASS |  |
| check-forbidden-patterns.py | FAIL | [forbidden-patterns] WARNINGS (commit allowed): backend\apps\auto_issues\management\commands\verify_autoissue_quota.py:202: [long-function] function `_quota_failure_message` is 73 lines (limit 50). Consider extracting helpers. |
| check-frontend-routes.py | FAIL | FAIL check-frontend-routes: HttpClient call points at a backend route that doesn't exist. frontend/src/app/core/services/auto-issues.service.ts:75: /api/auto-issues/ |
| check-gh-actions-read.py | PASS |  |
| check-glossary.py | FAIL | FAIL check-glossary: new technical terms found without a plain-English glossary entry. SSH â€” AI-CONTEXT.md:276 |
| check-go-service-contract.py | FAIL | FAIL check-go-service-contract: at least one services/<name>/ folder is missing its required artefacts. WHY: ADR 0006 § Decision (points 1 and 6) and docs/MODULAR-MONOLITH.md § Services tier (rules 1 and 4) require every Go service to publish: (a) ONE of api.proto / api.http.md as its public RPC contract, AND (b) cmd/<name>/main.go as its binary entry point. Library-only Go modules under services/ defeat the speed reason Go was chosen — they re-couple the build, encourage cross-language imports, and lose the sidecar deployment shape. |
| check-go-service-resource-budget.py | PASS |  |
| check-junk-files.py | PASS |  |
| check-lessons-read-at-session-start.py | PASS |  |
| check-lua-sandbox.py | PASS |  |
| check-lua-test-isolation.py | PASS |  |
| check-lua-test-sandbox.py | PASS |  |
| check-luajit-dialect.py | PASS |  |
| check-mgmt-command-dry-run.py | FAIL | FAIL check-mgmt-command-dry-run: management command(s) missing `--dry-run` flag. WHY: Rule H.H25 requires every Django management command that mutates state to support `--dry-run` so operators can preview what the command would do before letting it actually run. This prevents accidental data loss during maintenance jobs. |
| check-missing-tests.py | PASS |  |
| check-mutable-defaults.py | PASS |  |
| check-mutation-score.py | FAIL | usage: check-mutation-score.py [-h] --tool {mutmut,stryker,mull} --target TARGET --report REPORT [--seed-if-empty] |
| check-native-inspection-window.py | PASS |  |
| check-native-observability-wired.py | PASS |  |
| check-no-cross-language-import.py | PASS |  |
| check-no-deferral.py | FAIL | FAIL check-no-deferral: deferred work without a paper-trail or AutoIssue link is forbidden. WHY: the 2026-05-22 ABSOLUTE No-Deferral rule requires every deferred item to be filed in the database (paper trail or AutoIssue) so it cannot disappear into prose.  See `docs/specs/fr-observability-always-on-and-no-deferral.md`. |
| check-no-destructive-docker-commands.py | TIMEOUT | Hung and was killed after 20s. |
| check-no-downgraded-gates.py | PASS |  |
| check-no-duplicates-invariant.py | PASS |  |
| check-no-parallel-quality.py | PASS |  |
| check-no-rwx.py | PASS |  |
| check-no-verify-bypass.py | TIMEOUT | Hung and was killed after 20s. |
| check-observability-stack.py | FAIL | FAIL check-observability-stack: one or more observability or quality containers are not running. WHY: the 2026-05-22 ABSOLUTE rule `Observability + quality stack must always be running` forbids stopping any of these containers to dodge a hook, silence an importer, or bypass an honest check.  See `docs/specs/fr-observability-always-on-and-no-deferral.md`. |
| check-paper-trail-evidence.py | FAIL | FAIL check-paper-trail-evidence: missing per-entry Sticky #1 read marker for #14, #15. WHY: the 2026-05-23 Paper Trail 5-phase workflow requires `[STICKY 1 READ FOR PAPER-TRAIL: id=<N> ...]` before resolving a paper-trail entry. |
| check-paper-trail-read.py | FAIL | FAIL check-paper-trail-read: commit is missing the [PAPER TRAIL QUOTA VERIFIED: 10 resolved] marker. Run `manage.py verify_paper_trail_quota --ids <10 ids> --resolved-after <prev handoff timestamp>` and paste the result. |
| check-per-module-coverage.py | FAIL | FAIL check-per-module-coverage: coverage could not be measured for backend/apps/auto_issues/management/commands/auto_issues_append_registry.py, backend/apps/auto_issues/management/commands/measure_coverage.py, backend/apps/auto_issues/management/commands/print_open_issues.py, backend/apps/auto_issues/services/ci_failed_runs.py, backend/apps/auto_issues/services/contract_drift.py, backend/apps/auto_issues/services/dedup.py, backend/apps/auto_issues/services/fingerprinting.py, backend/apps/auto_issues/services/fuzz.py, backend/apps/auto_issues/services/lint_error.py, backend/apps/auto_issues/services/mutation.py, backend/apps/pipeline/services/hardware_profile.py (coverage tooling is unavailable or tests failed) |
| check-perf-proof.py | PASS |  |
| check-profiling-proof.py | PASS |  |
| check-recommended-preset-coverage.py | PASS |  |
| check-registry-read.py | FAIL | [31m[check-registry-read][0m FAIL: Code files are staged, but the quality result is not passing. Expected `guidelines=passed` and found `guidelines=focused`. Do not commit code with failing tests, unmet coverage, skipped mutation tests, missing tools, broken containers, unavailable checks, or known guideline violations. Fix the code or the check setup until every required value passes. |
| check-resolved-history.py | FAIL | FAIL check-resolved-history: 220 staged production source file(s) have NO disk-backed search_resolved_issues audit entry under task_id=f4c61529-f5bf-4330-a8bb-b72af57456c3. staged (no audit entry): .githooks/_hook_helpers.py |
| check-rewrite-quota.py | PASS |  |
| check-rust-mandate.py | PASS |  |
| check-scoped-lessons.py | PASS |  |
| check-session-close.py | FAIL | FAIL check-session-close: this commit starts a new session in AGENT-HANDOFF.md but the prior session's entry lacks a [SESSION CLOSE: ...] marker. WHY: PARAMOUNT TDD-pipeline rule says every session ends with `manage.py session_close` which verifies the session's lessons are logged and prunes the test-artefact prefixes (mull, coverage, mutmut, stryker, fuzz-work, pytest-debug). Skipping it leaves the next session inheriting hundreds of MiB of stale build output and breaks the chain of evidence that proves the previous TDD cycles were captured as lessons. |
| check-snapshotd-ritual.py | PASS |  |
| check-spec-citation.py | FAIL | FAIL check-spec-citation: SPEC PROOF status must be current or updated. WHY: code commits need a current SDD, PRD, or technical spec backed by patents, academic papers, or technical literature. |
| check-spec-window.py | PASS |  |
| check-sticky-1-read.py | PASS |  |
| check-stubs-not-regenerated.py | PASS |  |
| check-tdd-cycle.py | FAIL | FAIL check-tdd-cycle: production source files are staged but AGENT-HANDOFF.md is missing one [TDD CYCLE: file=<src> ...] marker per source file. WHY: Rule B requires strict Red-Green-Refactor TDD for every code change. The marker proves a failing test was written first (Red), the minimum source change made it pass (Green), and the touched file was refactored ruff-clean. One marker per source file -- no batch markers, no skipping. Generated stubs, test files, and .sh scripts are exempt; everything else is in. |
| check-tdd-preflight.py | PASS | [FINDING FILED: hook=check-tdd-preflight autoissue=#buffered severity=medium] |
| check-tdd-strict.py | TIMEOUT | Hung and was killed after 20s. |
| check-test-case-mandate.py | TIMEOUT | Hung and was killed after 20s. |


### Hooks summary
The following hooks failed or timed out:
- **check-autoissue-quota.py**: TIMEOUT
- **check-bundle-size.py**: Traceback (most recent call last): File "C:\Users\goldm\Dev\xf-internal-linker-v2\.githooks\check-bundle-size.py", line 130, in <module>
- **check-c-abi-conformance.py**: Exception in thread Thread-3 (_readerthread): Traceback (most recent call last):
- **check-code-review-lessons.py**: FAIL check-code-review-lessons: marker says only 12 file(s) reviewed but 220 production source file(s) are staged. WHY: Rule G requires every touched file to be accounted for in the review. The review must cover bugs, silent errors, correctness, tech debt, maintainability, duplication, and long functions.
- **check-commit-failures-lookup.py**: FAIL check-commit-failures-lookup: zero commit-failure lookups recorded for task_id=f4c61529-f5bf-4330-a8bb-b72af57456c3 in audit\commit_failures_lookup_log.jsonl. WHY: the 2026-05-18 user rule requires every agent to look up prior commit failures BEFORE committing, parallel to the per-file search_resolved_issues mandate. Without the lookup, the agent risks repeating a failure (timeout, orphan DB connection, missing marker, etc.) that an earlier session already diagnosed. A memory-only lookup does NOT satisfy the mandate; the audit log is the disk-backed evidence.
- **check-coverage-erosion.py**: TIMEOUT
- **check-file-size.py**: FAIL check-file-size: file(s) over the 1,500-line cap from CLAUDE.md. backend/apps/health/services.py: 2339 lines — over the 1500-line cap from CLAUDE.md. Split into named modules. If this file is being actively decomposed, add the path to .githooks/file-size-grandfather.txt with the current line count and remove it once the split lands.
- **check-forbidden-patterns.py**: [forbidden-patterns] WARNINGS (commit allowed): backend\apps\auto_issues\management\commands\verify_autoissue_quota.py:202: [long-function] function `_quota_failure_message` is 73 lines (limit 50). Consider extracting helpers.
- **check-frontend-routes.py**: FAIL check-frontend-routes: HttpClient call points at a backend route that doesn't exist. frontend/src/app/core/services/auto-issues.service.ts:75: /api/auto-issues/
- **check-glossary.py**: FAIL check-glossary: new technical terms found without a plain-English glossary entry. SSH â€” AI-CONTEXT.md:276
- **check-go-service-contract.py**: FAIL check-go-service-contract: at least one services/<name>/ folder is missing its required artefacts. WHY: ADR 0006 § Decision (points 1 and 6) and docs/MODULAR-MONOLITH.md § Services tier (rules 1 and 4) require every Go service to publish: (a) ONE of api.proto / api.http.md as its public RPC contract, AND (b) cmd/<name>/main.go as its binary entry point. Library-only Go modules under services/ defeat the speed reason Go was chosen — they re-couple the build, encourage cross-language imports, and lose the sidecar deployment shape.
- **check-mgmt-command-dry-run.py**: FAIL check-mgmt-command-dry-run: management command(s) missing `--dry-run` flag. WHY: Rule H.H25 requires every Django management command that mutates state to support `--dry-run` so operators can preview what the command would do before letting it actually run. This prevents accidental data loss during maintenance jobs.
- **check-mutation-score.py**: usage: check-mutation-score.py [-h] --tool {mutmut,stryker,mull} --target TARGET --report REPORT [--seed-if-empty]
- **check-no-deferral.py**: FAIL check-no-deferral: deferred work without a paper-trail or AutoIssue link is forbidden. WHY: the 2026-05-22 ABSOLUTE No-Deferral rule requires every deferred item to be filed in the database (paper trail or AutoIssue) so it cannot disappear into prose.  See `docs/specs/fr-observability-always-on-and-no-deferral.md`.
- **check-no-destructive-docker-commands.py**: TIMEOUT
- **check-no-verify-bypass.py**: TIMEOUT
- **check-observability-stack.py**: FAIL check-observability-stack: one or more observability or quality containers are not running. WHY: the 2026-05-22 ABSOLUTE rule `Observability + quality stack must always be running` forbids stopping any of these containers to dodge a hook, silence an importer, or bypass an honest check.  See `docs/specs/fr-observability-always-on-and-no-deferral.md`.
- **check-paper-trail-evidence.py**: FAIL check-paper-trail-evidence: missing per-entry Sticky #1 read marker for #14, #15. WHY: the 2026-05-23 Paper Trail 5-phase workflow requires `[STICKY 1 READ FOR PAPER-TRAIL: id=<N> ...]` before resolving a paper-trail entry.
- **check-paper-trail-read.py**: FAIL check-paper-trail-read: commit is missing the [PAPER TRAIL QUOTA VERIFIED: 10 resolved] marker. Run `manage.py verify_paper_trail_quota --ids <10 ids> --resolved-after <prev handoff timestamp>` and paste the result.
- **check-per-module-coverage.py**: FAIL check-per-module-coverage: coverage could not be measured for backend/apps/auto_issues/management/commands/auto_issues_append_registry.py, backend/apps/auto_issues/management/commands/measure_coverage.py, backend/apps/auto_issues/management/commands/print_open_issues.py, backend/apps/auto_issues/services/ci_failed_runs.py, backend/apps/auto_issues/services/contract_drift.py, backend/apps/auto_issues/services/dedup.py, backend/apps/auto_issues/services/fingerprinting.py, backend/apps/auto_issues/services/fuzz.py, backend/apps/auto_issues/services/lint_error.py, backend/apps/auto_issues/services/mutation.py, backend/apps/pipeline/services/hardware_profile.py (coverage tooling is unavailable or tests failed)
- **check-registry-read.py**: [31m[check-registry-read][0m FAIL: Code files are staged, but the quality result is not passing. Expected `guidelines=passed` and found `guidelines=focused`. Do not commit code with failing tests, unmet coverage, skipped mutation tests, missing tools, broken containers, unavailable checks, or known guideline violations. Fix the code or the check setup until every required value passes.
- **check-resolved-history.py**: FAIL check-resolved-history: 220 staged production source file(s) have NO disk-backed search_resolved_issues audit entry under task_id=f4c61529-f5bf-4330-a8bb-b72af57456c3. staged (no audit entry): .githooks/_hook_helpers.py
- **check-session-close.py**: FAIL check-session-close: this commit starts a new session in AGENT-HANDOFF.md but the prior session's entry lacks a [SESSION CLOSE: ...] marker. WHY: PARAMOUNT TDD-pipeline rule says every session ends with `manage.py session_close` which verifies the session's lessons are logged and prunes the test-artefact prefixes (mull, coverage, mutmut, stryker, fuzz-work, pytest-debug). Skipping it leaves the next session inheriting hundreds of MiB of stale build output and breaks the chain of evidence that proves the previous TDD cycles were captured as lessons.
- **check-spec-citation.py**: FAIL check-spec-citation: SPEC PROOF status must be current or updated. WHY: code commits need a current SDD, PRD, or technical spec backed by patents, academic papers, or technical literature.
- **check-tdd-cycle.py**: FAIL check-tdd-cycle: production source files are staged but AGENT-HANDOFF.md is missing one [TDD CYCLE: file=<src> ...] marker per source file. WHY: Rule B requires strict Red-Green-Refactor TDD for every code change. The marker proves a failing test was written first (Red), the minimum source change made it pass (Green), and the touched file was refactored ruff-clean. One marker per source file -- no batch markers, no skipping. Generated stubs, test files, and .sh scripts are exempt; everything else is in.
- **check-tdd-strict.py**: TIMEOUT
- **check-test-case-mandate.py**: TIMEOUT
