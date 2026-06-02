from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class MarketSnapshot:
    venue: str
    market_id: str
    question: str
    ticker: str | None = None
    slug: str | None = None
    yes_bid: float | None = None
    yes_ask: float | None = None
    no_bid: float | None = None
    no_ask: float | None = None
    yes_bid_size: float | None = None
    yes_ask_size: float | None = None
    no_bid_size: float | None = None
    no_ask_size: float | None = None
    liquidity: float | None = None
    volume_24h: float | None = None
    close_time: str | None = None
    rules: str | None = None
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def display_id(self) -> str:
        return self.ticker or self.slug or self.market_id


@dataclass(slots=True)
class MarketPair:
    pair_id: str
    polymarket: MarketSnapshot
    kalshi: MarketSnapshot
    confidence: float
    match_reason: str
    resolution_notes: str | None = None


@dataclass(slots=True)
class SignalLeg:
    venue: str
    market_id: str
    side: str
    price: float
    size: float | None = None
    url: str | None = None


@dataclass(slots=True)
class ArbitrageSignal:
    signal_id: str
    pair_id: str
    direction: str
    buy_yes_venue: str
    buy_no_venue: str
    market_title: str
    yes_ask: float
    no_ask: float
    gross_edge: float
    estimated_fees: float
    net_edge: float
    max_size: float
    estimated_profit: float
    confidence: float
    created_at: str
    legs: list[SignalLeg]
    warnings: list[str] = field(default_factory=list)
    category: str = "outros"
    yes_decimal_odds: float | None = None
    no_decimal_odds: float | None = None
    cost_per_contract: float | None = None
    max_total_stake: float | None = None


@dataclass(slots=True)
class ScannerSnapshot:
    updated_at: str | None = None
    status: str = "idle"
    error: str | None = None
    polymarket_count: int = 0
    kalshi_count: int = 0
    pair_count: int = 0
    signal_count: int = 0
    polymarket_markets: list[MarketSnapshot] = field(default_factory=list)
    kalshi_markets: list[MarketSnapshot] = field(default_factory=list)
    pairs: list[MarketPair] = field(default_factory=list)
    signals: list[ArbitrageSignal] = field(default_factory=list)
