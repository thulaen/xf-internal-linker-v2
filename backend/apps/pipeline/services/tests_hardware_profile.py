from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from apps.pipeline.services.hardware_profile import (
    HardwareProfile,
    detect_profile,
    refresh,
    recommended_batch_size,
    max_jobs_fast,
    max_jobs_heavy,
    polars_thread_count,
    _classify_tier,
    _tier_cap,
    _read_setting_override,
    _emit_json,
)

class _StopAfterGuard(Exception):
    pass

class HardwareProfileTests(SimpleTestCase):
    def setUp(self):
        import apps.pipeline.services.hardware_profile as hp
        self.original_cached = hp._cached_profile
        hp._cached_profile = None

    def tearDown(self):
        import apps.pipeline.services.hardware_profile as hp
        hp._cached_profile = self.original_cached

    @patch('psutil.virtual_memory')
    @patch('os.cpu_count')
    @patch('apps.pipeline.services.hardware_profile._read_setting_override')
    def test_detect_profile_no_override(self, mock_override, mock_cpu, mock_vm):
        mock_override.return_value = ""
        mock_cpu.return_value = 8
        mock_vm.return_value.total = 16 * 1e9
        
        prof = detect_profile()
        self.assertEqual(prof.ram_gb, 16.0)
        self.assertEqual(prof.cpu_cores, 8)
        self.assertEqual(prof.tier, "high")

    @patch('psutil.virtual_memory')
    @patch('apps.pipeline.services.hardware_profile._read_setting_override')
    def test_detect_profile_with_override(self, mock_override, mock_vm):
        mock_override.return_value = "low"
        mock_vm.return_value.total = 32 * 1e9
        
        prof = detect_profile()
        self.assertEqual(prof.tier, "low")

    def test_refresh_forces_detection(self):
        prof1 = detect_profile()
        prof2 = detect_profile()
        self.assertIs(prof1, prof2)

        with patch('apps.pipeline.services.hardware_profile._detect_ram_gb') as mock_ram:
            mock_ram.return_value = 4.0
            prof3 = refresh()
            self.assertIsNot(prof1, prof3)
            self.assertEqual(prof3.ram_gb, 4.0)

    def test_recommended_batch_size_capped(self):
        prof = HardwareProfile(ram_gb=128.0, cpu_cores=32, tier="workstation")
        batch = recommended_batch_size(dimension=1536, profile=prof)
        self.assertEqual(batch, 256)

    def test_recommended_batch_size_provider_ceiling(self):
        prof = HardwareProfile(ram_gb=128.0, cpu_cores=32, tier="workstation")
        batch = recommended_batch_size(dimension=1536, profile=prof, provider_ceiling=100)
        self.assertEqual(batch, 100)

    def test_max_jobs_fast(self):
        prof = HardwareProfile(ram_gb=4.0, cpu_cores=2, tier="low")
        self.assertEqual(max_jobs_fast(prof), 2)
        prof_ws = HardwareProfile(ram_gb=32.0, cpu_cores=8, tier="workstation")
        self.assertEqual(max_jobs_fast(prof_ws), 8)

    def test_max_jobs_heavy(self):
        prof = HardwareProfile(ram_gb=32.0, cpu_cores=8, tier="workstation")
        self.assertEqual(max_jobs_heavy(prof), 3)

    def test_polars_thread_count(self):
        prof = HardwareProfile(ram_gb=32.0, cpu_cores=8, tier="workstation")
        self.assertEqual(polars_thread_count(prof), 4)

    def test_classify_tier(self):
        self.assertEqual(_classify_tier(ram_gb=4.0), "low")
        self.assertEqual(_classify_tier(ram_gb=10.0), "medium")
        self.assertEqual(_classify_tier(ram_gb=20.0), "high")
        self.assertEqual(_classify_tier(ram_gb=64.0), "workstation")

    def test_tier_cap(self):
        self.assertEqual(_tier_cap("low"), 32)
        self.assertEqual(_tier_cap("medium"), 64)
        self.assertEqual(_tier_cap("high"), 128)
        self.assertEqual(_tier_cap("workstation"), 256)
        self.assertEqual(_tier_cap("unknown"), 64)

    @patch('apps.core.models.AppSetting.objects.filter')
    def test_read_setting_override(self, mock_filter):
        mock_qs = MagicMock()
        mock_filter.return_value = mock_qs
        mock_qs.first.return_value.value = " High "
        self.assertEqual(_read_setting_override(), "high")

    @patch('apps.core.models.AppSetting.objects.filter')
    def test_read_setting_override_logs_unavailable_setting_store(self, mock_filter):
        mock_filter.side_effect = RuntimeError("settings table unavailable")

        with self.assertLogs("apps.pipeline.services.hardware_profile", level="DEBUG") as logs:
            self.assertEqual(_read_setting_override(), "")

        self.assertTrue(any("performance profile override unavailable" in line for line in logs.output))

    def test_describe(self):
        prof = HardwareProfile(ram_gb=16.0, cpu_cores=8, tier="high")
        self.assertEqual(prof.describe(), "tier=high ram=16.0GB cores=8")

    def test_emit_json(self):
        prof = HardwareProfile(ram_gb=16.123, cpu_cores=8, tier="high")
        res = _emit_json(prof)
        import json
        parsed = json.loads(res)
        self.assertEqual(parsed["tier"], "high")
        self.assertEqual(parsed["cpu_cores"], 8)
        self.assertEqual(parsed["ram_gb"], 16.12)
        self.assertIn("max_jobs_fast", parsed)
        self.assertIn("max_jobs_heavy", parsed)
