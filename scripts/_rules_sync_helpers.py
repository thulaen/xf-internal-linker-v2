"""Shared helpers for agent-rule synchronization checks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "agent-rules-sync-manifest.yml"


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, list[str]]:
    current_key = ""
    manifest: dict[str, list[str]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(":") and not line.startswith("-"):
            current_key = line[:-1]
            manifest[current_key] = []
            continue
        if line.startswith("- ") and current_key:
            manifest[current_key].append(_clean_yaml_value(line[2:]))
    return manifest


def _clean_yaml_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip() + "\n"


def extract_section(text: str, anchor: str) -> str:
    lines = normalize_text(text).splitlines()
    start = _find_heading(lines, anchor)
    if start < 0:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if _is_shared_heading(lines[index]):
            end = index
            break
    return "\n".join(lines[start:end]).rstrip() + "\n"


def _find_heading(lines: list[str], anchor: str) -> int:
    needle = f"**{anchor}"
    for index, line in enumerate(lines):
        if line.startswith(needle):
            return index
    return -1


def _is_shared_heading(line: str) -> bool:
    return line.startswith("**ABSOLUTE — ") or line.startswith("**PARAMOUNT — ")


def read_agent_files(manifest: dict[str, list[str]]) -> dict[str, str]:
    return {
        rel_path: (ROOT / rel_path).read_text(encoding="utf-8")
        for rel_path in manifest["agent_files"]
    }


def diff_shared_sections(manifest: dict[str, list[str]]) -> list[str]:
    files = read_agent_files(manifest)
    errors: list[str] = []
    for anchor in manifest["shared_sections"]:
        sections = {path: extract_section(text, anchor) for path, text in files.items()}
        missing = [path for path, section in sections.items() if not section]
        if missing:
            errors.append(f"{anchor}: missing from {', '.join(missing)}")
            continue
        reference = next(iter(sections.values()))
        drifted = [path for path, section in sections.items() if section != reference]
        if drifted:
            errors.append(f"{anchor}: drift in {', '.join(drifted)}")
    return errors


def apply_shared_sections(manifest: dict[str, list[str]], source_file: str) -> list[str]:
    source_path = _resolve_agent_path(source_file)
    if not source_path.exists():
        return [f"{source_file}: source file does not exist"]
    source_text = source_path.read_text(encoding="utf-8")
    sections = {
        anchor: extract_section(source_text, anchor)
        for anchor in manifest["shared_sections"]
    }
    missing = [anchor for anchor, section in sections.items() if not section]
    if missing:
        return [f"{source_file}: missing shared section {anchor}" for anchor in missing]

    errors: list[str] = []
    ordered_sections = [
        (anchor, sections[anchor])
        for anchor in manifest["shared_sections"]
    ]
    for rel_path in manifest["agent_files"]:
        target_path = ROOT / rel_path
        if target_path == source_path:
            continue
        target_text = target_path.read_text(encoding="utf-8")
        updated = replace_shared_section_group(target_text, ordered_sections)
        if normalize_text(updated) != normalize_text(target_text):
            target_path.write_text(normalize_text(updated), encoding="utf-8")
    errors.extend(diff_shared_sections(manifest))
    return errors


def replace_section(text: str, anchor: str, replacement: str) -> str:
    lines = normalize_text(text).splitlines()
    start = _find_heading(lines, anchor)
    replacement_lines = normalize_text(replacement).splitlines()
    if start < 0:
        if lines and lines[-1]:
            lines.append("")
        lines.extend(replacement_lines)
        return "\n".join(lines).rstrip() + "\n"

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if _is_shared_heading(lines[index]):
            end = index
            break
    return "\n".join(lines[:start] + replacement_lines + lines[end:]).rstrip() + "\n"


def replace_shared_section_group(
    text: str,
    ordered_sections: list[tuple[str, str]],
) -> str:
    lines = normalize_text(text).splitlines()
    ranges = _shared_section_ranges(lines, [anchor for anchor, _ in ordered_sections])
    if not ranges:
        block = _shared_section_block(ordered_sections)
        if lines and lines[-1]:
            lines.append("")
        return "\n".join(lines + block).rstrip() + "\n"

    insert_at = min(start for start, _end in ranges)
    kept: list[str] = []
    insert_at_adjusted = 0
    for index, line in enumerate(lines):
        if _index_in_ranges(index, ranges):
            continue
        if index < insert_at:
            insert_at_adjusted += 1
        kept.append(line)

    block = _shared_section_block(ordered_sections)
    if insert_at_adjusted > 0 and kept[insert_at_adjusted - 1]:
        block = ["", *block]
    if insert_at_adjusted < len(kept) and kept[insert_at_adjusted]:
        block = [*block, ""]
    updated = kept[:insert_at_adjusted] + block + kept[insert_at_adjusted:]
    return "\n".join(updated).rstrip() + "\n"


def _shared_section_ranges(lines: list[str], anchors: list[str]) -> list[tuple[int, int]]:
    ranges = []
    for anchor in anchors:
        start = _find_heading(lines, anchor)
        if start >= 0:
            ranges.append((start, _section_end(lines, start)))
    return sorted(ranges)


def _section_end(lines: list[str], start: int) -> int:
    for index in range(start + 1, len(lines)):
        if _is_shared_heading(lines[index]):
            return index
    return len(lines)


def _index_in_ranges(index: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in ranges)


def _shared_section_block(ordered_sections: list[tuple[str, str]]) -> list[str]:
    block: list[str] = []
    for _anchor, section in ordered_sections:
        if block and block[-1]:
            block.append("")
        block.extend(normalize_text(section).splitlines())
    return block


def _resolve_agent_path(source_file: str) -> Path:
    path = Path(source_file)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()
