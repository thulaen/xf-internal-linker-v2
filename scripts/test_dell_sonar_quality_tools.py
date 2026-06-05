from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "scripts" / "start-dell-sonar-tools.ps1"
CHECK = ROOT / "scripts" / "check-dell-sonar-tools.ps1"
AUTOSCAN = ROOT / "scripts" / "dell-sonar-autoscan.sh"
MINT_START = ROOT / "scripts" / "start-mint-quality-tools.ps1"
MINT_CHECK = ROOT / "scripts" / "check-mint-quality-tools.ps1"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dell_sonar_start_script_exists() -> None:
    assert START.exists()
    assert AUTOSCAN.exists()


def test_dell_sonar_start_uses_dell_docker_context_and_named_volumes() -> None:
    text = _text(START)
    assert "docker --context dell" in text
    assert "sonarqube:community" in text
    assert "sonarsource/sonar-scanner-cli:latest" in text
    assert '"--entrypoint", "sh"' in text
    assert "xf_dell_sonar_repo" in text
    assert "xf_linker_sonarqube" in text
    assert "xf_linker_sonar_autoscan" in text
    assert "SONAR_HOST_URL=http://sonarqube:9000" in text


def test_dell_sonar_start_bootstraps_missing_network_without_stopping() -> None:
    text = _text(START)
    assert "ValueFromRemainingArguments" in text
    assert "$DockerArgs" in text
    assert "networkListArgs" in text
    assert '"network", "ls"' in text
    assert '$networkNames -contains "xf_dell_quality"' in text
    assert "if (-not $networkExists)" in text


def test_dell_sonar_start_removes_only_existing_containers() -> None:
    text = _text(START)
    assert "containerListArgs" in text
    assert '"container", "ls", "-a"' in text
    assert "xf_dell_sonar_repo_sync" in text
    assert "$existingContainers.Count -gt 0" in text
    assert '$removeArgs = @("rm", "-f") + @($existingContainers)' in text
    assert '"rm", "-f"' in text
    assert "Invoke-DellDocker @(" not in text


def test_dell_sonar_start_does_not_target_mint_or_bind_mount_msi_repo() -> None:
    text = _text(START).lower()
    assert "ssh mint" not in text
    assert "-v .:/repo" not in text
    assert "-v ${pwd}" not in text


def test_dell_sonar_start_syncs_tracked_source_without_generated_tree() -> None:
    text = _text(START)
    assert "git ls-files -z -- backend frontend sonar-project.properties" in text
    assert "printf '%s\\0' scripts/dell-sonar-autoscan.sh" in text
    assert "tar --null -T -" in text
    assert "backend/staticfiles" not in text
    assert "backend/media" not in text


def test_dell_sonar_autoscan_script_owns_loop_and_scanner_command() -> None:
    text = _text(AUTOSCAN)
    assert 'curl -fsS "$SONAR_HOST_URL/api/system/status"' in text
    assert 'curl -fsS "$SONAR_HOST_URL/api/server/version"' in text
    assert "sonar-scanner" in text
    assert "SONAR_AUTOSCAN_RETRY_SECONDS" in text
    assert 'sleep "$interval"' in text


def test_dell_sonar_check_script_verifies_health_and_recent_logs() -> None:
    text = _text(CHECK)
    assert "docker --context dell inspect" in text
    assert "docker --context dell exec xf_linker_sonarqube" in text
    assert "http://localhost:9000" in text
    assert "/api/system/status" in text
    assert "docker --context dell logs" in text
    assert '$ErrorActionPreference = "Continue"' in text
    assert "EXECUTION SUCCESS" in text


def test_mint_quality_scripts_no_longer_own_sonar() -> None:
    combined = (_text(MINT_START) + "\n" + _text(MINT_CHECK)).lower()
    assert "sonarqube" not in combined
    assert "sonar-autoscan" not in combined


SONAR_PROPERTIES = ROOT / "sonar-project.properties"


def _sonar_sources() -> list[str]:
    for line in _text(SONAR_PROPERTIES).splitlines():
        if line.strip().startswith("sonar.sources="):
            value = line.split("=", 1)[1].strip()
            return [part.strip() for part in value.split(",") if part.strip()]
    return []


def test_sonar_sources_only_reference_staged_scan_roots() -> None:
    # Both scanner paths — scripts/dell-sonar-autoscan.sh and the manual
    # sonar-scanner compose service — stage ONLY backend/ and frontend/ into
    # /tmp/sonar-src before invoking sonar-scanner. Every sonar.sources root
    # must therefore live under one of those trees, otherwise the scanner aborts
    # with "The folder '<name>' does not exist" and no analysis ever runs.
    roots = _sonar_sources()
    assert roots, "sonar.sources must be declared"
    for root in roots:
        assert root.startswith(("backend/", "frontend/")), (
            f"sonar.sources entry '{root}' is not staged by either scanner "
            "(only backend/ and frontend/ are copied into /tmp/sonar-src)"
        )
