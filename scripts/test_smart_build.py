import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _target_for_builder(builder):
    from scripts.smart_build import _select_builder_for_target

    config = json.loads((ROOT / "config/docker-build-routing.json").read_text(encoding="utf-8"))
    for index in range(1000):
        target = f"service-{index}"
        if _select_builder_for_target(target, config) == builder:
            return target
    raise AssertionError(f"No test target routed to {builder}")


class FakeRunner:
    def __init__(self, unavailable=None, current_context="desktop-linux"):
        self.commands = []
        self.unavailable = set(unavailable or [])
        self.current_context = current_context

    def __call__(self, command):
        self.commands.append(command)
        if command == ["docker", "context", "show"]:
            return 0, f"{self.current_context}\n", ""
        if command[:3] == ["docker", "buildx", "inspect"] and command[3] in self.unavailable:
            return 1, "", f"builder {command[3]} missing"
        return 0, "ok", ""


def test_non_gpu_build_uses_weighted_builder_and_never_cloud():
    """Given ordinary build, When helper runs, Then weighted builder is selected."""
    from scripts.smart_build import run

    runner = FakeRunner()
    target = _target_for_builder("mint")

    exit_code = run(["--target", target, "--", "--progress=plain"], runner=runner)

    assert exit_code == 0
    build_commands = [
        command for command in runner.commands
        if command[:4] == ["docker", "--context", command[2], "compose"]
    ]
    assert build_commands == [["docker", "--context", "mint", "compose", "build", "--progress=plain", target]]
    assert not any(command[:3] == ["docker", "context", "use"] for command in runner.commands)
    assert all("cloud" not in command for command in runner.commands)


def test_windows_never_routed_as_build_target():
    """Given the fail-closed build policy, When 1000 targets are routed, Then none land on Windows.

    MSI (desktop-linux) builds 0% — it never builds images for other machines.
    """
    from scripts.smart_build import _select_builder_for_target

    config = json.loads((ROOT / "config/docker-build-routing.json").read_text(encoding="utf-8"))
    routed = [_select_builder_for_target(f"service-{index}", config) for index in range(1000)]
    assert routed.count("desktop-linux") == 0


def test_mint_unavailable_fails_closed_without_windows_or_cloud_fallback(capsys):
    """Given Mint is unavailable, When ordinary build runs, Then helper fails closed."""
    from scripts.smart_build import run

    runner = FakeRunner(unavailable={"mint"})
    target = _target_for_builder("mint")

    exit_code = run(["--target", target], runner=runner)

    assert exit_code == 2
    assert ["docker", "context", "use", "desktop-linux"] not in runner.commands
    assert all("cloud" not in command for command in runner.commands)
    assert "Mint builder is not available" in capsys.readouterr().err


def test_select_only_switches_builder_without_running_build():
    """Given select-only mode, When helper runs, Then no image build starts."""
    from scripts.smart_build import run

    runner = FakeRunner()

    exit_code = run(["--select-only", "--target", "backend"], runner=runner)

    assert exit_code == 0
    assert not any(command[:3] == ["docker", "context", "use"] for command in runner.commands)
    assert not any("compose" in command and "build" in command for command in runner.commands)


def test_routing_config_routes_92_percent_to_dell_zero_to_windows():
    """Given routing config, When read, Then Dell carries 92%, Windows 0%, cloud off."""
    config = json.loads((ROOT / "config/docker-build-routing.json").read_text(encoding="utf-8"))

    assert config["builders"]["mint"] == "mint"
    assert config["builders"]["windows"] == "desktop-linux"
    assert config["builders"]["dell"] == "dell"
    machines = {entry["key"]: entry for entry in config["compilation_split"]["machines"]}
    assert machines["dell"]["percent"] == 92
    assert machines["dell"]["builder"] == "dell"
    assert machines["mint"]["percent"] == 8
    # MSI builds 0% — it never builds images for other machines.
    assert machines["windows"]["percent"] == 0
    assert sum(entry["percent"] for entry in config["compilation_split"]["machines"]) == 100
    assert config["fallback_policy"] == "fail_closed"
    assert "cloud" in config["disabled_builders"]


def test_weighted_split_is_stable_and_routes_about_92_percent_to_dell():
    """Given many targets, When routed, Then about 92 percent go to Dell and 0 to Windows."""
    from scripts.smart_build import _select_builder_for_target

    config = json.loads((ROOT / "config/docker-build-routing.json").read_text(encoding="utf-8"))

    routed = [
        _select_builder_for_target(f"service-{index}", config)
        for index in range(1000)
    ]

    # Dell carries ~92% (allow stable-hash drift); Mint still gets work; Windows gets none.
    assert 885 <= routed.count("dell") <= 950
    assert routed.count("mint") > 0
    assert routed.count("desktop-linux") == 0
    assert routed == [
        _select_builder_for_target(f"service-{index}", config)
        for index in range(1000)
    ]


def test_dell_routed_target_builds_on_dell_context():
    """Given a Dell-routed target, When the helper runs, Then it builds on the dell context."""
    from scripts.smart_build import run

    runner = FakeRunner()
    target = _target_for_builder("dell")

    exit_code = run(["--target", target, "--", "--progress=plain"], runner=runner)

    assert exit_code == 0
    assert ["docker", "--context", "dell", "compose", "build", "--progress=plain", target] in runner.commands
    assert all("cloud" not in command for command in runner.commands)


def test_dell_unavailable_fails_closed_naming_dell(capsys):
    """Given Dell is unavailable, When a Dell-routed build runs, Then it fails closed naming Dell."""
    from scripts.smart_build import run

    runner = FakeRunner(unavailable={"dell"})
    target = _target_for_builder("dell")

    exit_code = run(["--target", target], runner=runner)

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "Dell builder is not available" in err
    assert all("cloud" not in command for command in runner.commands)


def test_build_failure_reports_deduped_autoissue_payload():
    """Given compiler failure, When build exits non-zero, Then it reports once."""
    from scripts.smart_build import run

    class FailingRunner(FakeRunner):
        def __call__(self, command):
            self.commands.append(command)
            if command[:3] == ["docker", "buildx", "inspect"]:
                return 0, "ok", ""
            if command[:4] == ["docker", "--context", "mint", "compose"]:
                return 17, "compile started", "src/native.cpp:10: error: missing symbol"
            return 0, "reported", ""

    runner = FailingRunner()
    target = _target_for_builder("mint")

    exit_code = run(["--target", target], runner=runner)

    assert exit_code == 17
    report_commands = [
        command for command in runner.commands
        if command[0:6] == ["docker", "compose", "exec", "-T", "backend", "python"]
    ]
    assert len(report_commands) == 1
    payload = json.loads(report_commands[0][report_commands[0].index("--payload-json") + 1])
    assert payload["builder"] == "mint"
    assert payload["targets"] == [target]
    assert payload["exit_code"] == 17
    assert "missing symbol" in payload["stderr"]


def test_build_failure_report_can_be_disabled():
    """Given reporting disabled, When build fails, Then no AutoIssue command runs."""
    from scripts.smart_build import run

    class FailingRunner(FakeRunner):
        def __call__(self, command):
            self.commands.append(command)
            if command[:3] == ["docker", "buildx", "inspect"]:
                return 0, "ok", ""
            if command[:4] == ["docker", "--context", "mint", "compose"]:
                return 2, "", "compiler exploded"
            return 0, "reported", ""

    config = json.loads((ROOT / "config/docker-build-routing.json").read_text(encoding="utf-8"))
    config["failure_autoissues"]["enabled"] = False
    with NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        json.dump(config, handle)
        config_path = handle.name

    runner = FailingRunner()
    target = _target_for_builder("mint")

    exit_code = run(["--config", config_path, "--target", target], runner=runner)

    assert exit_code == 2
    assert not any("ingest_build_failure_autoissue" in command for command in runner.commands)


class _ImageMapRunner(FakeRunner):
    """FakeRunner that also answers `docker compose config --format json`."""

    def __init__(self, image_map, **kwargs):
        super().__init__(**kwargs)
        self.image_map = image_map

    def __call__(self, command):
        self.commands.append(command)
        if command == ["docker", "context", "show"]:
            return 0, f"{self.current_context}\n", ""
        if command[:3] == ["docker", "buildx", "inspect"] and command[3] in self.unavailable:
            return 1, "", f"builder {command[3]} missing"
        if command == ["docker", "compose", "config", "--format", "json"]:
            services = {name: {"image": img} for name, img in self.image_map.items()}
            return 0, json.dumps({"services": services}), ""
        return 0, "ok", ""


def test_mint_build_loads_image_into_local_docker():
    """Given a mint-built target, When the build succeeds, Then the image is streamed to local Docker."""
    from scripts.smart_build import run

    target = _target_for_builder("mint")
    runner = _ImageMapRunner({target: "xf-img:latest"})
    transfers = []

    def fake_transfer(image, src, dst):
        transfers.append((image, src, dst))
        return 0, f"Loaded image: {image}"

    exit_code = run(["--target", target], runner=runner, transfer=fake_transfer)

    assert exit_code == 0
    assert transfers == [("xf-img:latest", "mint", "desktop-linux")]


def test_local_builder_skips_image_load():
    """Given a build that ran on the local (Windows) builder, Then no transfer happens.

    Windows no longer routes any build, but the local-load skip path still guards
    a local build: when builder == the local builder the image is already present
    locally, so nothing is pulled.
    """
    from scripts.smart_build import _builder_name, _load_images_locally

    config = json.loads((ROOT / "config/docker-build-routing.json").read_text(encoding="utf-8"))
    local = _builder_name(config, "windows")
    transfers = []

    rc = _load_images_locally(
        builder=local, targets=["backend"], config=config,
        runner=_ImageMapRunner({"backend": "xf-img:latest"}),
        transfer=lambda image, src, dst: (transfers.append((image, src, dst)), (0, ""))[1],
    )

    assert rc == 0
    assert transfers == []


def test_failed_transfer_fails_the_build():
    """Given a mint build that builds OK but cannot load locally, Then the helper reports failure."""
    from scripts.smart_build import run

    target = _target_for_builder("mint")
    runner = _ImageMapRunner({target: "xf-img:latest"})

    exit_code = run(
        ["--target", target], runner=runner,
        transfer=lambda image, src, dst: (3, "no route to mint"),
    )

    assert exit_code == 3


def test_load_remote_images_can_be_disabled_via_config():
    """Given load_remote_images=false, When a mint build succeeds, Then no transfer is attempted."""
    from scripts.smart_build import run

    config = json.loads((ROOT / "config/docker-build-routing.json").read_text(encoding="utf-8"))
    config["load_remote_images"] = False
    with NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        json.dump(config, handle)
        config_path = handle.name

    target = _target_for_builder("mint")
    runner = _ImageMapRunner({target: "xf-img:latest"})
    transfers = []

    exit_code = run(
        ["--config", config_path, "--target", target], runner=runner,
        transfer=lambda image, src, dst: (transfers.append((image, src, dst)), (0, ""))[1],
    )

    assert exit_code == 0
    assert transfers == []


@pytest.mark.parametrize("filename", ["AGENTS.md", "CLAUDE.md", "CODEX.md", "GEMINI.md"])
def test_agent_docs_do_not_reference_old_auto_select_builder(filename):
    """Given agent docs, When read, Then old timed auto-switcher is gone."""
    text = (ROOT / filename).read_text(encoding="utf-8")

    assert "auto-select-builder.ps1" not in text
    assert "scripts/build-smart.ps1" in text


def test_tool_readiness_forced_builds_use_smart_build():
    """Given forced tool builds, When script runs, Then Smart Build routes them."""
    text = (ROOT / "scripts" / "run-tool-readiness.sh").read_text(encoding="utf-8")

    assert 'python scripts/smart_build.py --target "$service"' in text
    assert 'docker compose build "$service"' not in text


def test_bundle_size_hook_points_to_smart_build():
    """Given bundle guidance, When bundle is missing, Then Smart Build is shown."""
    text = (ROOT / ".githooks" / "check-bundle-size.py").read_text(encoding="utf-8")

    assert "scripts/build-smart.ps1 --target frontend-build" in text
    assert "docker compose build frontend-build" not in text
