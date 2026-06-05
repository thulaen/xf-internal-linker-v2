from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("check_rust_mandate.py")
spec = importlib.util.spec_from_file_location("check_rust_mandate", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


if __name__ == "__main__":
    raise SystemExit(module.main())
