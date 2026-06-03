import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_build_uses_production_environment_file():
    """Given prod build, When Angular compiles, Then prod URLs are used."""
    config = json.loads((ROOT / "frontend/angular.json").read_text(encoding="utf-8"))
    production = config["projects"]["xf-internal-linker-frontend"]["architect"]["build"][
        "configurations"
    ]["production"]

    replacements = production.get("fileReplacements", [])

    assert {
        "replace": "src/environments/environment.ts",
        "with": "src/environments/environment.production.ts",
    } in replacements
