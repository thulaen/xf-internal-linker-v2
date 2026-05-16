# quality-debt-ignore: reason: smoke tests for the 4 lifecycle helper commands live together at backend/apps/core/test_lifecycle_helpers.py because they share the same _repo_root() helper and fixture shape; co-locating them keeps the test surface small and avoids per-command duplication
"""Scaffold a new C++ kernel in all three Rule J lifecycle places at once.

Plain-English summary
---------------------

Adding a new C++ kernel requires three files to be edited together:

  1. `backend/extensions/<name>.cpp` — a new C++ source file with a
     `PYBIND11_MODULE(<name>, ...)` block.
  2. `scripts/ensure_compiled_artifacts.py` — the build step's
     `EXTENSION_NAMES` set must include `<name>`.
  3. `backend/apps/diagnostics/health.py` — the
     `_NATIVE_RUNTIME_MODULES` tuple must list `<name>`.

Forgetting any of those produces a "half-registered" kernel that
`.githooks/check-cpp-lifecycle.py` hard-blocks at commit. This command
does all three edits in one shot so the result is Rule-J compliant out
of the box.

What you get:

  - A minimal `.cpp` source with a `PYBIND11_MODULE` block that exports
    one callable named `--callable` (default: `ping`) returning the
    string `"<name>"`. You replace the body with the real
    implementation.
  - The new name inserted into `EXTENSION_NAMES` in sorted position.
  - The new tuple appended to `_NATIVE_RUNTIME_MODULES` with sensible
    defaults so the health check loads the kernel at boot.

Usage:

  docker compose exec -T backend python manage.py scaffold_cpp_kernel \
    --name my_new_kernel --description "What this kernel computes"
  docker compose exec -T backend python manage.py scaffold_cpp_kernel \
    --name my_new_kernel --dry-run

After scaffolding:

  1. Run `python manage.py audit_cpp_lifecycle --only-broken` — should
     show zero rows (the new kernel is fully registered).
  2. Implement the real body inside the `PYBIND11_MODULE` block.
  3. Add tests, a benchmark, and a spec citation.
  4. Commit. The full-tree Rule J hook will accept the change.
"""
# quality-debt-ignore: reason: shared imports across the 4 lifecycle helper commands are intentional — all four use BaseCommand + CommandError + repo_root from the shared helper module; consolidating imports further would push commands to import each other and create circular structure

from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ._lifecycle_helpers import repo_root as _repo_root

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _cpp_template(name: str, description: str, callable_name: str) -> str:
    return (
        f"// {name}.cpp - Scaffolded by manage.py scaffold_cpp_kernel.\n"
        f"// Replace this body with the real implementation, then add\n"
        f"// tests under backend/extensions/tests_{name}.py and a benchmark\n"
        f"// under backend/extensions/benchmarks/bench_{name}.cpp.\n"
        f"//\n"
        f"// Description: {description}\n"
        f"\n"
        f"#include <pybind11/pybind11.h>\n"
        f"#include <string>\n"
        f"\n"
        f"namespace py = pybind11;\n"
        f"\n"
        f"static std::string {callable_name}() {{\n"
        f'    return std::string("{name}");\n'
        f"}}\n"
        f"\n"
        f"PYBIND11_MODULE({name}, m) {{\n"
        f'    m.doc() = "{description}";\n'
        f'    m.def("{callable_name}", &{callable_name}, "Scaffold smoke-test callable.");\n'
        f"}}\n"
    )


def _insert_into_extension_names(text: str, name: str) -> str:
    """Insert `name` into the EXTENSION_NAMES = { ... } set in sorted position.

    The set is written one quoted name per line. We split at the closing
    brace, find the existing entries via regex, append the new one, and
    re-emit the block sorted.
    """
    pattern = re.compile(r"(EXTENSION_NAMES\s*=\s*\{)(?P<body>[^}]+)(\})", re.DOTALL)
    match = pattern.search(text)
    # quality-debt-ignore: reason: paired pattern.search() + None check appears in both _insert_into_extension_names and _insert_into_native_runtime because each helper has its own regex shape and its own CommandError message; abstracting the pair would force callers to handle a generic error and lose the specific "where did the block go" diagnostic
    if match is None:
        raise CommandError(
            "Could not find EXTENSION_NAMES = { ... } block in "
            "scripts/ensure_compiled_artifacts.py."
        )
    body = match.group("body")
    existing = set(re.findall(r"\"([a-z_][a-z0-9_]*)\"", body))
    if name in existing:
        return text  # idempotent
    existing.add(name)
    rebuilt_lines = [f'    "{n}",' for n in sorted(existing)]
    rebuilt = "\n" + "\n".join(rebuilt_lines) + "\n"
    return text[:match.start("body")] + rebuilt + text[match.end("body"):]


def _insert_into_native_runtime(
    text: str, name: str, callable_name: str, description: str
) -> str:
    """Append a new tuple to _NATIVE_RUNTIME_MODULES = ( ... ).

    Finds the closing `)` of the tuple (the one followed by a blank line
    and the next top-level definition) and inserts the new tuple line
    immediately before it.
    """
    pattern = re.compile(
        r"(_NATIVE_RUNTIME_MODULES\s*=\s*\()(?P<body>.+?)(\n\)\s*\n)",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        raise CommandError(
            "Could not find _NATIVE_RUNTIME_MODULES = ( ... ) block in "
            "backend/apps/diagnostics/health.py."
        )
    body = match.group("body")
    if re.search(rf'\(\s*"{re.escape(name)}"', body):
        return text  # idempotent
    new_tuple = f'    ("{name}", "{callable_name}", "{description}", False),'
    # body's last char is whatever comes before the captured "\n)", and the
    # tail starts at "\n)..." — so we just need a single newline between the
    # existing last tuple and the new one. No trailing newline (the captured
    # tail already starts with "\n").
    rebuilt_body = body.rstrip() + "\n" + new_tuple
    return text[:match.start("body")] + rebuilt_body + text[match.end("body"):]


class Command(BaseCommand):
    help = "Scaffold a new C++ kernel in all three Rule J lifecycle places at once."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Kernel name (lowercase, underscores).")
        parser.add_argument(
            "--callable",
            default="ping",
            dest="callable_name",
            help="Name of the exported pybind11 function (default: ping).",
        )
        parser.add_argument(
            "--description",
            default="TBD - replace with real description before committing",
            help="One-line description for the health-check label.",
        )
        # quality-debt-ignore: reason: Django add_arguments boilerplate is intentionally repetitive — each argument needs its own parser.add_argument call with its own help text; consolidating these would hide CLI documentation
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created/edited without writing any file.",
        )

    # quality-debt-ignore: reason: scaffold handle() validates two names, computes three target paths, calls two insertion helpers, prints the would-do plan, and (if not dry-run) writes the three artefacts; each step is tightly coupled to the file shape and splitting hurts readability
    def handle(self, *args, **options):
        name = options["name"]
        callable_name = options["callable_name"]
        description = options["description"]
        dry_run = options["dry_run"]

        if not NAME_RE.match(name):
            raise CommandError(
                f"Kernel name '{name}' must be lowercase letters, digits, and underscores, "
                f"starting with a letter."
            )
        if not NAME_RE.match(callable_name):
            raise CommandError(
                f"Callable name '{callable_name}' must be a valid C identifier "
                f"(lowercase + underscores)."
            )

        root = _repo_root()
        cpp_path = root / "backend" / "extensions" / f"{name}.cpp"
        ensure_path = root / "scripts" / "ensure_compiled_artifacts.py"
        health_path = root / "backend" / "apps" / "diagnostics" / "health.py"

        if cpp_path.exists():
            raise CommandError(
                f"{cpp_path.relative_to(root)} already exists. Pick a different name "
                f"or remove the existing file first."
            )

        cpp_content = _cpp_template(name, description, callable_name)
        ensure_text = ensure_path.read_text(encoding="utf-8")
        health_text = health_path.read_text(encoding="utf-8")
        new_ensure = _insert_into_extension_names(ensure_text, name)
        new_health = _insert_into_native_runtime(health_text, name, callable_name, description)

        self.stdout.write(f"scaffold_cpp_kernel: name={name} callable={callable_name}")
        self.stdout.write(f"  would create {cpp_path.relative_to(root)} ({len(cpp_content)} bytes)")
        if new_ensure != ensure_text:
            self.stdout.write(f"  would edit   {ensure_path.relative_to(root)} (insert into EXTENSION_NAMES)")
        else:
            self.stdout.write(f"  no change to {ensure_path.relative_to(root)} (name already present)")
        if new_health != health_text:
            self.stdout.write(f"  would edit   {health_path.relative_to(root)} (append to _NATIVE_RUNTIME_MODULES)")
        else:
            self.stdout.write(f"  no change to {health_path.relative_to(root)} (name already present)")

        # quality-debt-ignore: reason: self.stdout.write(...) is the Django BaseCommand-native way to emit lines to stdout; each line is a distinct user-facing message; consolidating into a loop hurts readability
        if dry_run:
            self.stdout.write("")
            self.stdout.write("Dry-run only - no files written. Re-run without --dry-run to apply.")
            return

        cpp_path.write_text(cpp_content, encoding="utf-8")
        if new_ensure != ensure_text:
            ensure_path.write_text(new_ensure, encoding="utf-8")
        if new_health != health_text:
            health_path.write_text(new_health, encoding="utf-8")

        self.stdout.write("")
        self.stdout.write(f"Created {cpp_path.relative_to(root)}.")
        self.stdout.write("Edited EXTENSION_NAMES and _NATIVE_RUNTIME_MODULES.")
        self.stdout.write("")
        self.stdout.write("Next steps:")
        self.stdout.write("  1. Run `python manage.py audit_cpp_lifecycle --only-broken` to confirm")
        self.stdout.write("     the new kernel shows 0 broken rows.")
        self.stdout.write(f"  2. Replace the body of {cpp_path.relative_to(root)} with the real")
        self.stdout.write("     implementation.")
        self.stdout.write(f"  3. Add tests under backend/extensions/tests_{name}.py and a")
        self.stdout.write(f"     benchmark under backend/extensions/benchmarks/bench_{name}.cpp.")
        self.stdout.write("  4. Add a spec entry citing the algorithm at docs/specs/<id>.md.")
