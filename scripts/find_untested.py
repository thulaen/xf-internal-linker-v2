import os

def find_untested_components(apps_dir):
    untested = []
    for root, dirs, files in os.walk(apps_dir):
        for f in files:
            if f.endswith('.component.ts') and not f.endswith('.spec.ts'):
                spec_file = f.replace('.ts', '.spec.ts')
                if not os.path.exists(os.path.join(root, spec_file)):
                    untested.append(os.path.join(root, f))
    return untested

if __name__ == "__main__":
    apps_dir = 'frontend/src/app'
    untested_components = find_untested_components(apps_dir)
    print(f"Found {len(untested_components)} untested components.")
    for c in untested_components[:30]:
        print(c)
