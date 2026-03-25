from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.content.models import ContentItem, ScopeItem, SiloGroup


class SiloApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="tester", password="pass")
        self.client.force_authenticate(user=user)

    def test_silo_group_delete_sets_scope_assignment_null(self):
        silo = SiloGroup.objects.create(name="Guitars", slug="guitars")
        scope = ScopeItem.objects.create(
            scope_id=101,
            scope_type="node",
            title="Electric Guitars",
            silo_group=silo,
        )

        response = self.client.delete(f"/api/silo-groups/{silo.pk}/")

        self.assertEqual(response.status_code, 204)
        scope.refresh_from_db()
        self.assertIsNone(scope.silo_group)

    def test_scope_patch_updates_only_silo_group(self):
        silo = SiloGroup.objects.create(name="Bass", slug="bass")
        scope = ScopeItem.objects.create(
            scope_id=201,
            scope_type="node",
            title="Bass Forum",
        )

        response = self.client.patch(
            f"/api/scopes/{scope.pk}/",
            {"silo_group": silo.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["silo_group"], silo.pk)
        self.assertEqual(response.json()["silo_group_name"], "Bass")
        scope.refresh_from_db()
        self.assertEqual(scope.silo_group_id, silo.pk)

    def test_silo_group_list_exposes_crud_contract_fields(self):
        silo = SiloGroup.objects.create(name="Keys", slug="keys", description="Keyboard content")
        ScopeItem.objects.create(scope_id=301, scope_type="node", title="Keys Forum", silo_group=silo)

        response = self.client.get("/api/silo-groups/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()[0],
            {
                "id": silo.pk,
                "name": "Keys",
                "slug": "keys",
                "description": "Keyboard content",
                "display_order": 0,
                "scope_count": 1,
                "created_at": response.json()[0]["created_at"],
                "updated_at": response.json()[0]["updated_at"],
            },
        )

    def test_silo_settings_defaults_and_validation(self):
        response = self.client.get("/api/settings/silos/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "mode": "disabled",
                "same_silo_boost": 0.0,
                "cross_silo_penalty": 0.0,
            },
        )

        valid = self.client.put(
            "/api/settings/silos/",
            {
                "mode": "prefer_same_silo",
                "same_silo_boost": 0.2,
                "cross_silo_penalty": 0.1,
            },
            format="json",
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["mode"], "prefer_same_silo")

        invalid = self.client.put(
            "/api/settings/silos/",
            {
                "mode": "strict",
                "same_silo_boost": 0.2,
                "cross_silo_penalty": 0.1,
            },
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)


class ContentMarch2026PageRankApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="content-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_content_endpoints_expose_march_2026_pagerank_score(self):
        scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")
        content = ContentItem.objects.create(
            content_id=123,
            content_type="thread",
            title="March Destination",
            scope=scope,
            march_2026_pagerank_score=0.25,
        )

        list_response = self.client.get("/api/content/")
        detail_response = self.client.get(f"/api/content/{content.pk}/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(list_response.json()["results"][0]["march_2026_pagerank_score"], 0.25)
        self.assertEqual(detail_response.json()["march_2026_pagerank_score"], 0.25)
