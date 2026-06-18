"""Tiny Cobertura XML coverage parser for distributed reports."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def line_rate(path: Path) -> float:
    """Return the Cobertura line-rate value as a percentage."""
    root = ET.parse(path).getroot()
    return float(root.attrib.get("line-rate", "0")) * 100.0
