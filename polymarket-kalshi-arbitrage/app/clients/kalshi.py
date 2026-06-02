from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path
from typing import Any

import httpx

from app.models import MarketSnapshot
from app.settings import ApiSettings
from app.utils import as_float, clamp_price


class KalshiClient:
    def __init__(self, settings: ApiSettings):
        self.settings = settings
        self.headers = {"User-Agent": settings.user_agent}

    async def fetch_markets(
        self,
        limit: int | None = 250,
        page_size: int = 1000,
        max_pages: int | None = 50,
        max_concurrent_requests: int = 8,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> list[MarketSnapshot]:
        target_limit = None if limit is None or limit <= 0 else limit
        page_size = max(1, min(page_size, 1000))
        max_pages = None if max_pages is None or max_pages <= 0 else max_pages
        max_concurrent_requests = max(1, max_concurrent_requests)
        timeout = httpx.Timeout(self.settings.request_timeout_seconds)
        limits = httpx.Limits(
            max_connections=max_concurrent_requests,
            max_keepalive_connections=max_concurrent_requests,
        )
        markets: list[MarketSnapshot] = []
        cursor: str | None = None
        pages_fetched = 0

        async with httpx.AsyncClient(timeout=timeout, headers=self.headers, limits=limits) as client:
            while target_limit is None or len(markets) < target_limit:
                if max_pages is not None and pages_fetched >= max_pages:
                    break

                page_limit = page_size
                if target_limit is not None:
                    page_limit = min(page_limit, target_limit - len(markets))
                params: dict[str, Any] = {
                    "status": "open",
                    "mve_filter": "exclude",
                    "limit": page_limit,
                }
                if cursor:
                    params["cursor"] = cursor

                payload = await self._get_json(
                    client,
                    f"{self.settings.kalshi_base}/markets",
                    params,
                    retry_attempts,
                    retry_backoff_seconds,
                )
                raw_markets = payload.get("markets", [])
                markets.extend(self._parse_market(item) for item in raw_markets)
                markets = [market for market in markets if market is not None]
                pages_fetched += 1

                cursor = payload.get("cursor") or None
                if not cursor or not raw_markets:
                    break

        return markets if target_limit is None else markets[:target_limit]

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any],
        retry_attempts: int,
        retry_backoff_seconds: float,
    ) -> dict[str, Any]:
        for attempt in range(retry_attempts + 1):
            response = await client.get(url, params=params)
            if response.status_code not in {429, 500, 502, 503, 504} or attempt >= retry_attempts:
                response.raise_for_status()
                return response.json()

            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else retry_backoff_seconds * (2**attempt)
            except ValueError:
                delay = retry_backoff_seconds * (2**attempt)
            await asyncio.sleep(max(0.0, delay))

        raise RuntimeError("unreachable retry branch")

    def _parse_market(self, item: dict[str, Any]) -> MarketSnapshot | None:
        ticker = item.get("ticker")
        title = item.get("title") or item.get("subtitle") or item.get("yes_sub_title")
        if not ticker or not title:
            return None

        yes_bid = clamp_price(as_float(item.get("yes_bid_dollars")))
        yes_ask = clamp_price(as_float(item.get("yes_ask_dollars")))
        no_bid = clamp_price(as_float(item.get("no_bid_dollars")))
        no_ask = clamp_price(as_float(item.get("no_ask_dollars")))

        if no_ask is None and yes_bid is not None:
            no_ask = clamp_price(1.0 - yes_bid)
        if no_bid is None and yes_ask is not None:
            no_bid = clamp_price(1.0 - yes_ask)

        return MarketSnapshot(
            venue="kalshi",
            market_id=str(ticker),
            question=str(title).strip(),
            ticker=str(ticker),
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            no_bid=no_bid,
            no_ask=no_ask,
            yes_bid_size=as_float(item.get("yes_bid_size_fp")),
            yes_ask_size=as_float(item.get("yes_ask_size_fp")),
            liquidity=as_float(item.get("liquidity_dollars")),
            volume_24h=as_float(item.get("volume_24h_fp")),
            close_time=item.get("close_time") or item.get("expiration_time"),
            rules="\n\n".join(filter(None, [item.get("rules_primary"), item.get("rules_secondary")])) or None,
            url=f"https://kalshi.com/markets/{ticker}",
            metadata={
                "category": item.get("category"),
                "event_ticker": item.get("event_ticker"),
                "series_ticker": item.get("series_ticker"),
                "title": item.get("title"),
                "subtitle": item.get("subtitle"),
                "yes_sub_title": item.get("yes_sub_title"),
            },
        )


class KalshiSigner:
    """Helper for authenticated endpoints such as orderbooks and order entry."""

    def __init__(self, api_key_id: str, private_key_pem: str | None = None, private_key_path: str | None = None):
        self.api_key_id = api_key_id
        self.private_key_pem = private_key_pem
        self.private_key_path = private_key_path

    def headers(self, method: str, path: str) -> dict[str, str]:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ModuleNotFoundError as exc:
            raise RuntimeError("Install cryptography to use Kalshi authenticated endpoints.") from exc

        timestamp_ms = str(int(time.time() * 1000))
        message = f"{timestamp_ms}{method.upper()}{path}".encode("utf-8")
        private_key = serialization.load_pem_private_key(self._load_private_key_bytes(), password=None)
        signature = private_key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii"),
        }

    def _load_private_key_bytes(self) -> bytes:
        if self.private_key_pem:
            return self.private_key_pem.encode("utf-8")
        if self.private_key_path:
            return Path(self.private_key_path).read_bytes()
        raise ValueError("Provide either private_key_pem or private_key_path.")
