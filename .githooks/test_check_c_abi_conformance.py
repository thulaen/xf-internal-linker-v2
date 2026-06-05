"""Tests for the C ABI conformance hook."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "check-c-abi-conformance.py"


def run_hook(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK), "--check-files", *map(str, paths)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_accepts_versioned_prefixed_noexcept_header(tmp_path: Path) -> None:
    header = tmp_path / "backend/extensions/example/include/xf_example.h"
    header.parent.mkdir(parents=True)
    header.write_text(
        """
#include <stdint.h>
#define XF_API
#define XF_NOEXCEPT noexcept
typedef uint32_t xf_status_t;
extern "C" {
typedef struct xf_example_config {
  uint32_t abi_size;
  uint32_t abi_version;
  uint32_t flags;
} xf_example_config;
XF_API xf_status_t xf_example_run(const xf_example_config *config) XF_NOEXCEPT;
}
""",
        encoding="utf-8",
    )
    result = run_hook(header)
    assert result.returncode == 0, result.stderr


def test_rejects_public_struct_without_abi_version_fields(tmp_path: Path) -> None:
    header = tmp_path / "backend/extensions/example/include/xf_example.h"
    header.parent.mkdir(parents=True)
    header.write_text(
        """
#include <stdint.h>
#define XF_API
#define XF_NOEXCEPT noexcept
typedef uint32_t xf_status_t;
extern "C" {
typedef struct xf_example_config {
  uint32_t flags;
} xf_example_config;
XF_API xf_status_t xf_example_run(const xf_example_config *config) XF_NOEXCEPT;
}
""",
        encoding="utf-8",
    )
    result = run_hook(header)
    assert result.returncode == 1
    assert "abi_size" in result.stderr


def test_rejects_export_without_noexcept_marker(tmp_path: Path) -> None:
    header = tmp_path / "backend/extensions/example/include/xf_example.h"
    header.parent.mkdir(parents=True)
    header.write_text(
        """
#include <stdint.h>
#define XF_API
typedef uint32_t xf_status_t;
extern "C" {
typedef struct xf_example_config {
  uint32_t abi_size;
  uint32_t abi_version;
} xf_example_config;
XF_API xf_status_t xf_example_run(const xf_example_config *config);
}
""",
        encoding="utf-8",
    )
    result = run_hook(header)
    assert result.returncode == 1
    assert "XF_NOEXCEPT" in result.stderr

