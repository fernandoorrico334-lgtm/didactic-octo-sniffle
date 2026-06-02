from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from typing import Any


def as_float(value: Any) -> float | None:
    if value in (None, "", "NaN"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def clamp_price(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, value))


def dataclass_to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: dataclass_to_dict(item) for key, item in value.items()}
    return value


def slugify(text: str, max_length: int = 80) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    if len(normalized) <= max_length:
        return normalized
    return normalized[:max_length].strip("-")

