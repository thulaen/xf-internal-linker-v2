from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("check_rust_mandate.py")
spec = importlib.util.spec_from_file_location("check_rust_mandate", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
# Register before exec_module: the logic module defines a @dataclass, and
# dataclasses resolves field annotations via sys.modules[cls.__module__]. A
# module loaded with module_from_spec is NOT auto-registered, so without this
# line the dataclass decorator raises AttributeError on a None lookup. This is
# the standard importlib.util.module_from_spec idiom (see the Python docs).
sys.modules[spec.name] = module
spec.loader.exec_module(module)


if __name__ == "__main__":
    raise SystemExit(module.main())
