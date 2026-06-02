from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from app.clients.kalshi import KalshiClient
from app.clients.polymarket import PolymarketClient
from app.models import ScannerSnapshot, utc_now_iso
from app.services.arbitrage import find_arbitrage_signals
from app.services.matcher import load_manual_pair_specs, match_markets
from app.services.simulation import simulated_kalshi_markets, simulated_polymarket_markets
from app.settings import Settings


logger = logging.getLogger(__name__)


def _has_actionable_prices(market) -> bool:
    return market.yes_ask is not None and market.no_ask is not None


def _passes_market_filters(market, settings: Settings) -> bool:
    if not market.question or not _has_actionable_prices(market):
        return False

    min_liquidity = settings.scanner.min_market_liquidity
    if min_liquidity > 0 and (market.liquidity or 0.0) < min_liquidity:
        return False

    min_volume = settings.scanner.min_market_volume_24h
    if min_volume > 0 and (market.volume_24h or 0.0) < min_volume:
        return False

    return True


def _prefilter_markets(markets, settings: Settings):
    return [market for market in markets if _passes_market_filters(market, settings)]


class MarketScanner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.polymarket = PolymarketClient(settings.api)
        self.kalshi = KalshiClient(settings.api)
        self.snapshot = ScannerSnapshot()
        self._lock = asyncio.Lock()
        self._background_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def scan_once(self) -> ScannerSnapshot:
        async with self._lock:
            self.snapshot.status = "scanning"
            self.snapshot.error = None
            try:
                if self.settings.scanner.data_mode == "simulation":
                    polymarkets = simulated_polymarket_markets()
                    kalshis = simulated_kalshi_markets()
                else:
                    polymarkets, kalshis = await asyncio.gather(
                        self.polymarket.fetch_markets(
                            limit=self.settings.scanner.polymarket_limit,
                            page_size=self.settings.scanner.polymarket_page_size,
                            max_pages=self.settings.scanner.max_pages_per_venue,
                            max_concurrent_requests=self.settings.scanner.max_concurrent_requests,
                            retry_attempts=self.settings.scanner.retry_attempts,
                            retry_backoff_seconds=self.settings.scanner.retry_backoff_seconds,
                            include_orderbooks=self.settings.scanner.include_polymarket_orderbooks,
                        ),
                        self.kalshi.fetch_markets(
                            limit=self.settings.scanner.kalshi_limit,
                            page_size=self.settings.scanner.kalshi_page_size,
                            max_pages=self.settings.scanner.max_pages_per_venue,
                            max_concurrent_requests=self.settings.scanner.max_concurrent_requests,
                            retry_attempts=self.settings.scanner.retry_attempts,
                            retry_backoff_seconds=self.settings.scanner.retry_backoff_seconds,
                        ),
                    )

                match_polymarkets = _prefilter_markets(polymarkets, self.settings)
                match_kalshis = _prefilter_markets(kalshis, self.settings)

                manual_specs = load_manual_pair_specs(self.settings.manual_pairs_path)
                pairs = match_markets(
                    match_polymarkets,
                    match_kalshis,
                    min_confidence=self.settings.scanner.min_match_confidence,
                    manual_specs=manual_specs,
                    candidate_limit_per_market=self.settings.scanner.match_candidate_limit_per_market,
                    max_auto_pairs=self.settings.scanner.max_auto_pairs,
                )
                signals = find_arbitrage_signals(pairs, self.settings.scanner)
                self.snapshot = ScannerSnapshot(
                    updated_at=utc_now_iso(),
                    status="ok",
                    polymarket_count=len(polymarkets),
                    kalshi_count=len(kalshis),
                    pair_count=len(pairs),
                    signal_count=len(signals),
                    polymarket_markets=polymarkets,
                    kalshi_markets=kalshis,
                    pairs=pairs,
                    signals=signals,
                )
            except Exception as exc:  # noqa: BLE001 - surface scan failures to API health.
                logger.exception("scan failed")
                self.snapshot = replace(
                    self.snapshot,
                    updated_at=utc_now_iso(),
                    status="error",
                    error=str(exc),
                )
            return self.snapshot

    def latest(self) -> ScannerSnapshot:
        return self.snapshot

    async def start_background(self) -> None:
        if self._background_task and not self._background_task.done():
            return
        self._stop_event.clear()
        self._background_task = asyncio.create_task(self._run_loop())

    async def stop_background(self) -> None:
        self._stop_event.set()
        if self._background_task:
            await self._background_task

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            await self.scan_once()
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.settings.scanner.interval_seconds,
                )
            except TimeoutError:
                continue
