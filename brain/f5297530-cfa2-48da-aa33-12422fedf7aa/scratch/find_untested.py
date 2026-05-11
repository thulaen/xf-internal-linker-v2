import os
from pathlib import Path

def find_untested_components():
    frontend_dir = Path("frontend/src/app")
    untested = []
    for root, dirs, files in os.walk(frontend_dir):
        for file in files:
            if file.endswith(".component.ts") and not file.endswith(".spec.ts"):
                comp_path = Path(root) / file
                spec_path = comp_path.with_suffix(".spec.ts")
                if not spec_path.exists():
                    untested.append(str(comp_path))
    return untested

if __name__ == "__main__":
    untested = find_untested_components()
    for u in sorted(untested):
        print(u)
