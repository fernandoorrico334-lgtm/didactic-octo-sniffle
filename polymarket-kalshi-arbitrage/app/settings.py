from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_MANUAL_PAIRS_PATH = PROJECT_ROOT / "config" / "manual_pairs.yaml"


@dataclass(slots=True)
class ScannerSettings:
    data_mode: str = "simulation"
    autostart: bool = True
    interval_seconds: int = 45
    polymarket_limit: int = 0
    kalshi_limit: int = 0
    polymarket_page_size: int = 500
    kalshi_page_size: int = 1000
    max_pages_per_venue: int = 50
    max_concurrent_requests: int = 8
    retry_attempts: int = 2
    retry_backoff_seconds: float = 0.5
    include_polymarket_orderbooks: bool = False
    min_match_confidence: float = 0.58
    min_net_edge: float = 0.01
    max_position_size: float = 25.0
    unknown_liquidity_size: float = 5.0
    polymarket_fee_bps: float = 0.0
    kalshi_fee_bps: float = 0.0
    signal_limit: int = 50


@dataclass(slots=True)
class ApiSettings:
    polymarket_gamma_base: str = "https://gamma-api.polymarket.com"
    polymarket_clob_base: str = "https://clob.polymarket.com"
    kalshi_base: str = "https://external-api.kalshi.com/trade-api/v2"
    request_timeout_seconds: float = 12.0
    user_agent: str = "polymarket-kalshi-arbitrage/0.1"


@dataclass(slots=True)
class Settings:
    scanner: ScannerSettings = field(default_factory=ScannerSettings)
    api: ApiSettings = field(default_factory=ApiSettings)
    manual_pairs_path: Path = DEFAULT_MANUAL_PAIRS_PATH


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PyYAML is required to read config/settings.yaml. "
            "Install dependencies with: pip install -r requirements.txt"
        ) from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def _coerce_path(raw: str | None, fallback: Path) -> Path:
    if not raw:
        return fallback
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def load_settings(config_path: str | Path | None = None) -> Settings:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    raw = _load_yaml(path)
    scanner_raw = raw.get("scanner", {})
    api_raw = raw.get("api", {})

    scanner = ScannerSettings(**{k: v for k, v in scanner_raw.items() if hasattr(ScannerSettings, k)})
    api = ApiSettings(**{k: v for k, v in api_raw.items() if hasattr(ApiSettings, k)})

    if os.getenv("ARBITRAGE_DATA_MODE"):
        scanner.data_mode = str(os.environ["ARBITRAGE_DATA_MODE"])
    if os.getenv("ARBITRAGE_AUTOSTART"):
        scanner.autostart = os.environ["ARBITRAGE_AUTOSTART"].lower() in {"1", "true", "yes", "on"}

    manual_pairs_path = _coerce_path(raw.get("manual_pairs_path"), DEFAULT_MANUAL_PAIRS_PATH)
    return Settings(scanner=scanner, api=api, manual_pairs_path=manual_pairs_path)
