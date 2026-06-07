import unittest
from unittest.mock import patch, MagicMock
from scripts.agent_live_stream import get_active_container

class TestAgentLiveStream(unittest.TestCase):
    @patch("subprocess.run")
    def test_get_active_container_finds_mutation(self, mock_run):
        # Given output with a quality container
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="12345abcde\txf_linker_quality_python\txf-linker-backend-quality:latest\n67890fghij\txf_linker_postgres\tpgvector/pgvector:pg17\n"
        )
        
        # When
        result = get_active_container()
        
        # Then
        self.assertEqual(result, ("12345abcde", "xf_linker_quality_python"))

    @patch("subprocess.run")
    def test_get_active_container_finds_mutmut(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="aaaaabbbbb\txf_linker_mutmut_runner\txf-linker-backend-quality:latest\n"
        )
        result = get_active_container()
        self.assertEqual(result, ("aaaaabbbbb", "xf_linker_mutmut_runner"))

    @patch("subprocess.run")
    def test_get_active_container_no_match(self, mock_run):
        # Given output with no quality/mutation containers
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="12345abcde\txf_linker_nginx\tnginx:latest\n67890fghij\txf_linker_postgres\tpgvector/pgvector:pg17\n"
        )
        
        # When
        result = get_active_container()
        
        # Then
        self.assertIsNone(result)

    @patch("subprocess.run")
    def test_get_active_container_finds_quality_image_with_random_name(self, mock_run):
        # Given Docker assigned a random name, but the image is a quality image
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc123\tbrave_newton\txf-linker-backend-quality:latest\n"
        )

        # When
        result = get_active_container()

        # Then
        self.assertEqual(result, ("abc123", "brave_newton"))

if __name__ == "__main__":
    unittest.main()
