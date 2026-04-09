import json
import logging
import os
from typing import Any, Dict, Generator
from django.conf import settings

logger = logging.getLogger(__name__)


def import_from_jsonl(file_path: str) -> Generator[Dict[str, Any], None, None]:
    """
    Read a JSONL file line-by-line and yield records.

    Security:
    - Validates that the file exists and is a file.
    - Path traversal protection: Ensures the file is within the project root.
    - Memory efficiency: Reads line-by-line using a generator.
    """
    # Security: Path traversal protection
    abs_root = os.path.abspath(settings.BASE_DIR.parent)
    abs_file = os.path.abspath(file_path)
    if not abs_file.startswith(abs_root):
        logger.error(
            "JSONL import failed: Security - Blocked access to file outside root: %s",
            file_path,
        )
        raise PermissionError(f"Access denied: {file_path}")

    if not os.path.isfile(abs_file):
        logger.error("JSONL import failed: File not found at %s", abs_file)
        raise FileNotFoundError(f"JSONL file not found: {abs_file}")

    logger.info("Starting JSONL import from %s...", abs_file)

    with open(abs_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                logger.error("JSONL parse error at line %d: %s", line_num, str(e))
                continue
