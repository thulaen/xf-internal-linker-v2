"""DB-free tests for the Embeddings-page backend endpoints.

The heavy view bodies talk to ``AppSetting``, ledgers, and Celery; those
paths are exercised elsewhere. Here we lock the pure helpers
(``_mask_secret``, the key lists) and the branches that resolve without
the database: the GET provider list, the invalid-provider rejection, the
masked-settings GET, and the bake-off sample-size clamp. Every database,
Celery, and config read is mocked.

These are ``@api_view`` function views, so we build real DRF requests
with ``APIRequestFactory`` (no Django test client, no database) and call
the views with authentication forced off via a patched permission check.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.api import embedding_views as ev

_factory = APIRequestFactory()


def _user() -> SimpleNamespace:
    return SimpleNamespace(is_authenticated=True, is_active=True, pk=1)


class MaskSecretTests(SimpleTestCase):
    def test_when_empty_then_empty_string(self) -> None:
        self.assertEqual(ev._mask_secret(""), "")

    def test_when_eight_chars_then_all_masked(self) -> None:
        self.assertEqual(ev._mask_secret("12345678"), "********")

    def test_when_exactly_at_boundary_then_no_tail_shown(self) -> None:
        # len == 8 is the <= 8 branch: fully masked, no trailing reveal.
        self.assertEqual(ev._mask_secret("abcdefgh"), "********")

    def test_when_longer_than_eight_then_last_four_visible(self) -> None:
        self.assertEqual(ev._mask_secret("sk-secret-key-1234"), "**************1234")

    def test_when_nine_chars_then_five_stars_plus_last_four(self) -> None:
        self.assertEqual(ev._mask_secret("123456789"), "*****6789")


class ConfigKeyConstantTests(SimpleTestCase):
    def test_when_secret_keys_then_only_api_key(self) -> None:
        self.assertEqual(ev._SECRET_KEYS, {"embedding.api_key"})

    def test_when_provider_keys_then_exact_pair(self) -> None:
        self.assertEqual(
            ev._PROVIDER_KEYS,
            ["embedding.provider", "embedding.fallback_provider"],
        )

    def test_when_config_keys_then_api_key_present(self) -> None:
        self.assertIn("embedding.api_key", ev._PROVIDER_CONFIG_KEYS)
        self.assertEqual(len(ev._PROVIDER_CONFIG_KEYS), 18)


class EmbeddingProviderGetTests(SimpleTestCase):
    def _get(self):
        req = _factory.get("/api/embedding/provider/")
        force_authenticate(req, user=_user())
        return req

    def _post(self, data):
        req = _factory.post("/api/embedding/provider/", data, format="json")
        force_authenticate(req, user=_user())
        return req

    def test_when_get_then_returns_active_fallback_available(self) -> None:
        with patch.object(ev, "_get_setting", return_value=""):
            resp = ev.embedding_provider(self._get())
        self.assertEqual(
            resp.data,
            {"active": "openai", "fallback": "openai", "available": ["openai", "gemini"]},
        )

    def test_when_get_with_settings_then_uses_those_values(self) -> None:
        with patch.object(ev, "_get_setting", return_value="gemini"):
            resp = ev.embedding_provider(self._get())
        self.assertEqual(resp.data["active"], "gemini")
        self.assertEqual(resp.data["available"], ["openai", "gemini"])

    def test_when_post_invalid_provider_then_400(self) -> None:
        resp = ev.embedding_provider(self._post({"name": "anthropic"}))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {"detail": "invalid provider"})

    def test_when_post_local_provider_then_400_local_no_longer_allowed(self) -> None:
        # "local" was a valid member before the diff; the changed membership
        # tuple is exactly ("openai", "gemini"). A swap back to including
        # "local" would let this through, so the rejection must be exact.
        resp = ev.embedding_provider(self._post({"name": "local"}))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {"detail": "invalid provider"})

    def test_when_post_empty_name_then_400(self) -> None:
        resp = ev.embedding_provider(self._post({"name": ""}))
        self.assertEqual(resp.status_code, 400)

    def _accept_with_mocked_db(self, name: str):
        """Drive the valid-provider accept path with the DB + cache mocked.

        Kills the negation of ``if name not in (...)`` in the True
        direction: if ``not in`` flips to ``in`` a valid name would 400.
        """
        fake_appsetting = SimpleNamespace(
            objects=SimpleNamespace(update_or_create=MagicMock())
        )
        core_models = SimpleNamespace(AppSetting=fake_appsetting)
        providers = SimpleNamespace(clear_cache=MagicMock())
        with patch.dict(
            "sys.modules",
            {
                "apps.core.models": core_models,
                "apps.pipeline.services.embedding_providers": providers,
            },
        ):
            return ev.embedding_provider(self._post({"name": name})), fake_appsetting

    def test_when_post_valid_openai_then_accepted_and_persisted(self) -> None:
        resp, fake_appsetting = self._accept_with_mocked_db("openai")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"active": "openai"})
        fake_appsetting.objects.update_or_create.assert_called_once_with(
            key="embedding.provider", defaults={"value": "openai"}
        )

    def test_when_post_valid_gemini_then_accepted(self) -> None:
        resp, _ = self._accept_with_mocked_db("gemini")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"active": "gemini"})


class EmbeddingStatusDefaultProviderTests(SimpleTestCase):
    """Lock the ``or "openai"`` defaults in ``embedding_status``.

    The diff changed the no-setting fallback from ``"local"`` to ``"openai"``
    for both the active provider and the fallback. With every heavy
    collaborator mocked and ``_get_setting`` returning ``""``, the response
    must carry exactly ``"openai"`` for both — an exact assertEqual kills a
    string wrap and a swap back to ``"local"``.
    """

    def _status_with_no_settings(self):
        profile = SimpleNamespace(tier="t", ram_gb=1.0, cpu_cores=1)

        ledger_qs = MagicMock()
        ledger_qs.filter.return_value = ledger_qs
        ledger_qs.values.return_value = ledger_qs
        ledger_qs.annotate.return_value = []
        ledger = SimpleNamespace(objects=ledger_qs)
        pipeline_models = SimpleNamespace(
            EmbeddingCostLedger=ledger,
            EmbeddingBakeoffResult=MagicMock(),
            EmbeddingGateDecision=MagicMock(),
        )

        hw = SimpleNamespace(
            detect_profile=MagicMock(return_value=profile),
            recommended_batch_size=MagicMock(return_value=4),
        )
        providers = SimpleNamespace(get_provider=MagicMock(side_effect=Exception()))

        content_qs = MagicMock()
        content_qs.filter.return_value = content_qs
        content_qs.count.return_value = 0
        content_models = SimpleNamespace(ContentItem=SimpleNamespace(objects=content_qs))

        req = _factory.get("/api/embedding/status/")
        force_authenticate(req, user=_user())
        with (
            patch.object(ev, "_get_setting", return_value=""),
            patch.dict(
                "sys.modules",
                {
                    "apps.pipeline.models": pipeline_models,
                    "apps.pipeline.services.hardware_profile": hw,
                    "apps.pipeline.services.embedding_providers": providers,
                    "apps.content.models": content_models,
                },
            ),
        ):
            return ev.embedding_status(req)

    def test_when_no_provider_setting_then_active_is_openai(self) -> None:
        resp = self._status_with_no_settings()
        self.assertEqual(resp.data["active_provider"], "openai")

    def test_when_no_fallback_setting_then_fallback_is_openai(self) -> None:
        resp = self._status_with_no_settings()
        self.assertEqual(resp.data["fallback_provider"], "openai")


class EmbeddingStatusProviderSuccessTests(SimpleTestCase):
    def test_when_provider_and_content_exist_then_status_reports_counts(self) -> None:
        provider = SimpleNamespace(
            dimension=1536,
            signature="openai:small",
            model_name="text-embedding-3-small",
            max_tokens=8192,
        )
        profile = SimpleNamespace(tier="high", ram_gb=16.44, cpu_cores=20)
        ledger_qs = MagicMock()
        ledger_qs.filter.return_value = ledger_qs
        ledger_qs.values.return_value = ledger_qs
        ledger_qs.annotate.return_value = [
            {"provider": "openai", "total": 1.25, "tokens": 1000}
        ]
        content_qs = MagicMock()
        content_qs.filter.return_value = content_qs
        content_qs.count.side_effect = [10, 7]
        req = _factory.get("/api/embedding/status/")
        force_authenticate(req, user=_user())
        with (
            patch.object(
                ev,
                "_get_setting",
                side_effect=lambda key: {
                    "embedding.provider": "openai",
                    "embedding.fallback_provider": "gemini",
                    "embedding.recommended_provider": "openai",
                }.get(key, ""),
            ),
            patch.dict(
                "sys.modules",
                {
                    "apps.pipeline.models": SimpleNamespace(
                        EmbeddingCostLedger=SimpleNamespace(objects=ledger_qs)
                    ),
                    "apps.pipeline.services.hardware_profile": SimpleNamespace(
                        detect_profile=MagicMock(return_value=profile),
                        recommended_batch_size=MagicMock(return_value=64),
                    ),
                    "apps.pipeline.services.embedding_providers": SimpleNamespace(
                        get_provider=MagicMock(return_value=provider)
                    ),
                    "apps.content.models": SimpleNamespace(
                        ContentItem=SimpleNamespace(objects=content_qs)
                    ),
                },
            ),
        ):
            resp = ev.embedding_status(req)
        self.assertEqual(resp.data["dimension"], 1536)
        self.assertEqual(resp.data["signature"], "openai:small")
        self.assertEqual(resp.data["coverage"], {"total": 10, "embedded": 7, "pct": 70.0})
        self.assertEqual(resp.data["spend_this_month"][0]["cost_usd"], 1.25)


class EmbeddingHardwareProfileTests(SimpleTestCase):
    def test_when_requested_then_common_batch_sizes_returned(self) -> None:
        profile = SimpleNamespace(tier="high", ram_gb=15.55, cpu_cores=20)
        req = _factory.get("/api/embedding/hardware-profile/")
        force_authenticate(req, user=_user())
        with patch.dict(
            "sys.modules",
            {
                "apps.pipeline.services.hardware_profile": SimpleNamespace(
                    detect_profile=MagicMock(return_value=profile),
                    recommended_batch_size=MagicMock(side_effect=lambda dimension, profile: dimension // 512),
                )
            },
        ):
            resp = ev.embedding_hardware_profile(req)
        self.assertEqual(resp.data["tier"], "high")
        self.assertEqual(resp.data["batch_sizes"], {"1024": 2, "1536": 3, "3072": 6})


class EmbeddingTestConnectionDefaultTests(SimpleTestCase):
    """Lock the ``or "openai"`` defaults in ``embedding_test_connection``.

    With no ``provider`` in the body and ``_get_setting`` returning ``""``,
    the tested provider name must default to ``"openai"`` — the response
    echoes ``provider`` so an exact assertEqual kills the changed default.
    """

    def test_when_no_provider_in_body_then_defaults_to_openai(self) -> None:
        fake_provider = SimpleNamespace(
            healthcheck=MagicMock(), signature="sig-openai"
        )
        providers = SimpleNamespace(
            get_provider=MagicMock(return_value=fake_provider),
            clear_cache=MagicMock(),
        )
        fake_appsetting = SimpleNamespace(
            objects=SimpleNamespace(update_or_create=MagicMock())
        )
        core_models = SimpleNamespace(AppSetting=fake_appsetting)
        req = _factory.post("/api/embedding/test-connection/", {}, format="json")
        force_authenticate(req, user=_user())
        with (
            patch.object(ev, "_get_setting", return_value=""),
            patch.dict(
                "sys.modules",
                {
                    "apps.pipeline.services.embedding_providers": providers,
                    "apps.core.models": core_models,
                },
            ),
        ):
            resp = ev.embedding_test_connection(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["provider"], "openai")
        self.assertEqual(resp.data, {"ok": True, "provider": "openai", "signature": "sig-openai"})


class EmbeddingSettingsGetTests(SimpleTestCase):
    def test_when_get_then_api_key_is_masked_others_raw(self) -> None:
        def fake_get(key: str) -> str:
            return "sk-secret-key-1234" if key == "embedding.api_key" else "plain"

        req = _factory.get("/api/embedding/settings/")
        force_authenticate(req, user=_user())
        with patch.object(ev, "_get_setting", side_effect=fake_get):
            resp = ev.embedding_settings(req)
        self.assertEqual(resp.data["embedding.api_key"], "**************1234")
        self.assertEqual(resp.data["embedding.model"], "plain")

    def test_when_post_then_only_allowed_non_null_settings_are_saved(self) -> None:
        fake_appsetting = SimpleNamespace(
            objects=SimpleNamespace(update_or_create=MagicMock())
        )
        clear_cache = MagicMock()
        req = _factory.post(
            "/api/embedding/settings/",
            {
                "embedding.model": "model-a",
                "embedding.api_key": None,
                "not.allowed": "ignored",
            },
            format="json",
        )
        force_authenticate(req, user=_user())
        with patch.dict(
            "sys.modules",
            {
                "apps.core.models": SimpleNamespace(AppSetting=fake_appsetting),
                "apps.pipeline.services.embedding_providers": SimpleNamespace(
                    clear_cache=clear_cache
                ),
            },
        ):
            resp = ev.embedding_settings(req)
        self.assertEqual(resp.data, {"ok": True})
        fake_appsetting.objects.update_or_create.assert_called_once_with(
            key="embedding.model", defaults={"value": "model-a"}
        )
        clear_cache.assert_called_once()


class EmbeddingTestConnectionFailureTests(SimpleTestCase):
    def test_when_healthcheck_fails_then_previous_provider_is_restored(self) -> None:
        provider = SimpleNamespace(
            healthcheck=MagicMock(side_effect=RuntimeError("bad key")),
            signature="sig",
        )
        fake_appsetting = SimpleNamespace(
            objects=SimpleNamespace(update_or_create=MagicMock())
        )
        clear_cache = MagicMock()
        req = _factory.post(
            "/api/embedding/test-connection/",
            {"provider": "gemini"},
            format="json",
        )
        force_authenticate(req, user=_user())
        with (
            patch.object(ev, "_get_setting", return_value="openai"),
            patch.dict(
                "sys.modules",
                {
                    "apps.core.models": SimpleNamespace(AppSetting=fake_appsetting),
                    "apps.pipeline.services.embedding_providers": SimpleNamespace(
                        get_provider=MagicMock(return_value=provider),
                        clear_cache=clear_cache,
                    ),
                },
            ),
        ):
            resp = ev.embedding_test_connection(req)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["error"], "bad key")
        self.assertEqual(fake_appsetting.objects.update_or_create.call_count, 2)
        fake_appsetting.objects.update_or_create.assert_any_call(
            key="embedding.provider", defaults={"value": "gemini"}
        )
        fake_appsetting.objects.update_or_create.assert_any_call(
            key="embedding.provider", defaults={"value": "openai"}
        )


class EmbeddingBakeoffRunTests(SimpleTestCase):
    def _post(self, data):
        req = _factory.post("/api/embedding/bakeoff/run/", data, format="json")
        force_authenticate(req, user=_user())
        return req

    def test_when_garbage_sample_size_then_clamped_to_default_1000(self) -> None:
        fake_task = MagicMock()
        fake_task.delay.return_value = SimpleNamespace(id="task-1")
        fake_module = SimpleNamespace(embedding_provider_bakeoff=fake_task)
        with patch.dict(
            "sys.modules",
            {"apps.pipeline.tasks_embedding_bakeoff": fake_module},
        ):
            resp = ev.embedding_bakeoff_run(self._post({"sample_size": "foo"}))
        self.assertEqual(resp.data, {"task_id": "task-1"})
        fake_task.delay.assert_called_once_with(sample_size=1000)

    def test_when_oversized_sample_size_then_clamped_to_max(self) -> None:
        fake_task = MagicMock()
        fake_task.delay.return_value = SimpleNamespace(id="task-2")
        fake_module = SimpleNamespace(embedding_provider_bakeoff=fake_task)
        with patch.dict(
            "sys.modules",
            {"apps.pipeline.tasks_embedding_bakeoff": fake_module},
        ):
            ev.embedding_bakeoff_run(self._post({"sample_size": 9_999_999}))
        fake_task.delay.assert_called_once_with(sample_size=200_000)


class EmbeddingProviderEvalRunTests(SimpleTestCase):
    def _post(self, data):
        req = _factory.post("/api/embedding/provider-evaluations/run/", data, format="json")
        force_authenticate(req, user=_user())
        return req

    def test_when_cost_not_confirmed_then_400_and_no_task(self) -> None:
        resp = ev.embedding_provider_eval_run(self._post({"sample_size": 10}))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {"detail": "cost confirmation required"})

    def test_when_cost_confirmed_then_task_starts(self) -> None:
        fake_task = MagicMock()
        fake_task.delay.return_value = SimpleNamespace(id="task-3")
        fake_module = SimpleNamespace(embedding_provider_bakeoff=fake_task)
        with patch.dict(
            "sys.modules",
            {"apps.pipeline.tasks_embedding_bakeoff": fake_module},
        ):
            resp = ev.embedding_provider_eval_run(
                self._post({"sample_size": "25", "cost_confirmed": True})
            )
        self.assertEqual(resp.data, {"task_id": "task-3", "sample_size": 25})
        fake_task.delay.assert_called_once_with(sample_size=25)


class EmbeddingProviderEvalGroupingTests(SimpleTestCase):
    def test_when_rows_share_job_then_grouped_under_one_run(self) -> None:
        rows = [
            {
                "job_id": "run-1",
                "provider": "openai",
                "sample_size": 5,
                "mrr_at_10": 0.5,
                "verdict": "winner",
            },
            {
                "job_id": "run-1",
                "provider": "gemini",
                "sample_size": 5,
                "mrr_at_10": 0.4,
                "is_banned": True,
            },
        ]
        grouped = ev._group_provider_score_rows(rows)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["job_id"], "run-1")
        self.assertEqual(len(grouped[0]["providers"]), 2)
        self.assertEqual(grouped[0]["providers"][1]["verdict"], "unknown")
        self.assertTrue(grouped[0]["providers"][1]["is_banned"])

    def test_when_row_has_no_job_id_then_skipped(self) -> None:
        self.assertEqual(ev._group_provider_score_rows([{"provider": "openai"}]), [])


class _ValuesRows:
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)

    def __getitem__(self, item):
        return self.rows[item]


class _FakeRows:
    def __init__(self, rows):
        self.rows = rows
        self.order_args = ()
        self.value_fields = ()

    def order_by(self, *args):
        self.order_args = args
        return self

    def values(self, *fields):
        self.value_fields = fields
        if not fields:
            return _ValuesRows(self.rows)
        return _ValuesRows([{field: row.get(field) for field in fields} for row in self.rows])


class EmbeddingProviderEvalListTests(SimpleTestCase):
    def test_when_eval_runs_requested_then_rows_are_grouped(self) -> None:
        rows = _FakeRows([
            {"job_id": "run-1", "provider": "openai", "sample_size": 3},
            {"job_id": "run-1", "provider": "gemini", "sample_size": 3},
        ])
        req = _factory.get("/api/embedding/provider-evaluations/")
        force_authenticate(req, user=_user())
        with patch.dict(
            "sys.modules",
            {
                "apps.pipeline.models": SimpleNamespace(
                    EmbeddingBakeoffResult=SimpleNamespace(objects=rows)
                )
            },
        ):
            resp = ev.embedding_provider_eval_runs(req)
        self.assertEqual(resp.data["runs"][0]["job_id"], "run-1")
        self.assertEqual(len(resp.data["runs"][0]["providers"]), 2)
        self.assertEqual(rows.order_args, ("-created_at",))
        self.assertIn("provider", rows.value_fields)


class EmbeddingBakeoffResultListTests(SimpleTestCase):
    def test_when_bakeoff_results_requested_then_recent_rows_returned(self) -> None:
        rows = _FakeRows([{"provider": "openai"}, {"provider": "gemini"}])
        req = _factory.get("/api/embedding/bakeoff/")
        force_authenticate(req, user=_user())
        with patch.dict(
            "sys.modules",
            {
                "apps.pipeline.models": SimpleNamespace(
                    EmbeddingBakeoffResult=SimpleNamespace(objects=rows)
                )
            },
        ):
            resp = ev.embedding_bakeoff_results(req)
        self.assertEqual(resp.data, [{"provider": "openai"}, {"provider": "gemini"}])
        self.assertEqual(rows.order_args, ("-created_at",))


class EmbeddingProviderUnbanTests(SimpleTestCase):
    def _post(self, data):
        req = _factory.post("/api/embedding/provider/unban/", data, format="json")
        force_authenticate(req, user=_user())
        return req

    def test_when_provider_invalid_then_400(self) -> None:
        resp = ev.embedding_provider_unban(self._post({"provider": "local"}))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {"detail": "invalid provider"})

    def test_when_provider_valid_then_removed_from_ban_list(self) -> None:
        fake_appsetting = SimpleNamespace(
            get_str=MagicMock(return_value='["openai", "gemini"]'),
            objects=SimpleNamespace(update_or_create=MagicMock()),
        )
        core_models = SimpleNamespace(AppSetting=fake_appsetting)
        with patch.dict("sys.modules", {"apps.core.models": core_models}):
            resp = ev.embedding_provider_unban(self._post({"provider": "gemini"}))

        self.assertEqual(resp.data, {"provider": "gemini", "is_banned": False})
        fake_appsetting.objects.update_or_create.assert_called_once_with(
            key="embedding.provider_bans_json",
            defaults={"value": '["openai"]'},
        )

    def test_when_ban_list_is_not_json_list_then_treated_as_empty(self) -> None:
        fake_appsetting = SimpleNamespace(
            get_str=MagicMock(return_value='"gemini"'),
            objects=SimpleNamespace(update_or_create=MagicMock()),
        )
        core_models = SimpleNamespace(AppSetting=fake_appsetting)
        with patch.dict("sys.modules", {"apps.core.models": core_models}):
            resp = ev.embedding_provider_unban(self._post({"provider": "gemini"}))

        self.assertEqual(resp.data, {"provider": "gemini", "is_banned": False})
        fake_appsetting.objects.update_or_create.assert_called_once_with(
            key="embedding.provider_bans_json",
            defaults={"value": "[]"},
        )


class EmbeddingTaskEndpointTests(SimpleTestCase):
    def test_when_audit_run_requested_then_manual_audit_task_starts(self) -> None:
        fake_task = MagicMock()
        fake_task.delay.return_value = SimpleNamespace(id="audit-1")
        req = _factory.post("/api/embedding/audit/run/", {}, format="json")
        force_authenticate(req, user=_user())
        with patch.dict(
            "sys.modules",
            {
                "apps.pipeline.tasks_embedding_audit": SimpleNamespace(
                    embedding_accuracy_audit=fake_task
                )
            },
        ):
            resp = ev.embedding_audit_run(req)
        self.assertEqual(resp.data, {"task_id": "audit-1"})
        fake_task.delay.assert_called_once_with(fortnightly=False, force=True)

    def test_when_gate_decisions_requested_then_recent_rows_returned(self) -> None:
        rows = _FakeRows([{"provider": "openai", "decision": "passed"}])
        req = _factory.get("/api/embedding/gate-decisions/")
        force_authenticate(req, user=_user())
        with patch.dict(
            "sys.modules",
            {
                "apps.pipeline.models": SimpleNamespace(
                    EmbeddingGateDecision=SimpleNamespace(objects=rows)
                )
            },
        ):
            resp = ev.embedding_gate_decisions(req)
        self.assertEqual(resp.data, [{"provider": "openai", "decision": "passed"}])
        self.assertEqual(rows.order_args, ("-created_at",))
