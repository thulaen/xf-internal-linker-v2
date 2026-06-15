from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model


class AdvancedGraphSignalsSettingsViewTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpassword123",
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("settings-advanced-graph-signals")

    def test_get_settings_success(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data
        self.assertIn("tosd", data)
        self.assertIn("dstp", data)
        self.assertIn("icpc", data)
        self.assertIn("sbma", data)
        self.assertIn("rgsd", data)
        self.assertIn("csbr", data)

        self.assertIn("enabled", data["tosd"])
        self.assertIn("ranking_weight", data["tosd"])
        self.assertIn("filter_strength", data["tosd"])

    def test_put_settings_success(self):
        payload = {
            "tosd": {
                "enabled": False,
                "ranking_weight": 0.15,
                "filter_strength": 0.5,
            },
            "dstp": {
                "enabled": True,
                "ranking_weight": 0.20,
                "smoothing_alpha": 4.0,
            },
        }

        response = self.client.put(self.url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data["tosd"]["enabled"], False)
        self.assertEqual(data["tosd"]["ranking_weight"], 0.15)
        self.assertEqual(data["tosd"]["filter_strength"], 0.5)

        self.assertEqual(data["dstp"]["enabled"], True)
        self.assertEqual(data["dstp"]["ranking_weight"], 0.20)
        self.assertEqual(data["dstp"]["smoothing_alpha"], 4.0)
        
        # Verify it persisted
        response2 = self.client.get(self.url)
        self.assertEqual(response2.data["tosd"]["enabled"], False)
        self.assertEqual(response2.data["tosd"]["ranking_weight"], 0.15)
        self.assertEqual(response2.data["tosd"]["filter_strength"], 0.5)

    def test_put_settings_clamping(self):
        payload = {
            "icpc": {
                "enabled": "invalid_bool", # coerced to True/False, but invalid gets defaults or current
                "ranking_weight": 1.0, # clamped to max 0.25
                "min_community_size": 1000000, # clamped to 100000
            },
            "rgsd": {
                "curvature_penalty": "not_a_float", # gets default
            }
        }

        response = self.client.put(self.url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data
        self.assertEqual(data["icpc"]["ranking_weight"], 0.25)
        self.assertEqual(data["icpc"]["min_community_size"], 100000)
        
        # Original default for rgsd.curvature_penalty is 1.5
        self.assertEqual(data["rgsd"]["curvature_penalty"], 1.5)

    def test_get_settings_unauthenticated(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put_settings_unauthenticated(self):
        self.client.logout()
        response = self.client.put(self.url, data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
