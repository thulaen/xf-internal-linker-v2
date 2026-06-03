"""Convention SimpleTestCase coverage for apps.health.views module surface.

The GPU endpoint (`HealthGpuView`) was deleted along with the rest of the
GPU/CUDA code. These no-DB tests pin the module's public class surface so
a future edit cannot silently re-add the removed GPU view or drop one of
the remaining view classes. Import-level assertions only — no client, no
database, no network.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.health import views


class ViewsModuleSurfaceTests(SimpleTestCase):
    def test_when_gpu_view_removed_then_attribute_absent(self):
        self.assertFalse(hasattr(views, "HealthGpuView"))

    def test_when_module_imported_then_status_viewset_present(self):
        self.assertTrue(hasattr(views, "HealthStatusViewSet"))

    def test_when_module_imported_then_disk_view_present(self):
        self.assertTrue(hasattr(views, "HealthDiskView"))

    def test_when_status_viewset_then_lookup_field_is_service_key(self):
        self.assertEqual(views.HealthStatusViewSet.lookup_field, "service_key")

    def test_when_status_viewset_then_pagination_disabled(self):
        self.assertIsNone(views.HealthStatusViewSet.pagination_class)
