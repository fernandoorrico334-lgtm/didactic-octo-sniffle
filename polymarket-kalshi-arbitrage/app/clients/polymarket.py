from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.models import MarketSnapshot
from app.settings import ApiSettings
from app.utils import as_float, clamp_price, parse_jsonish


class PolymarketClient:
    def __init__(self, settings: ApiSettings):
        self.settings = settings
        self.headers = {"User-Agent": settings.user_agent}

    async def fetch_markets(
        self,
        limit: int | None = 250,
        page_size: int = 500,
        max_pages: int | None = 50,
        max_concurrent_requests: int = 8,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 0.5,
        include_orderbooks: bool = False,
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
        async with httpx.AsyncClient(timeout=timeout, headers=self.headers, limits=limits) as client:
            snapshots = await self._fetch_keyset_markets(
                client,
                target_limit,
                page_size,
                max_pages,
                retry_attempts,
                retry_backoff_seconds,
            )

            if include_orderbooks:
                await self._hydrate_orderbooks(
                    client,
                    snapshots,
                    max_concurrent_requests,
                    retry_attempts,
                    retry_backoff_seconds,
                )

            return snapshots

    async def _fetch_keyset_markets(
        self,
        client: httpx.AsyncClient,
        target_limit: int | None,
        page_size: int,
        max_pages: int | None,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> list[MarketSnapshot]:
        markets: list[MarketSnapshot] = []
        seen: set[str] = set()
        after_cursor: str | None = None
        pages_fetched = 0

        while target_limit is None or len(markets) < target_limit:
            if max_pages is not None and pages_fetched >= max_pages:
                break

            page_limit = page_size
            if target_limit is not None:
                page_limit = min(page_limit, target_limit - len(markets))

            params = {
                "active": "true",
                "closed": "false",
                "limit": str(page_limit),
                "order": "volume_24hr",
                "ascending": "false",
            }
            if after_cursor:
                params["after_cursor"] = after_cursor

            payload = await self._get_json(
                client,
                f"{self.settings.polymarket_gamma_base}/markets/keyset",
                params,
                retry_attempts,
                retry_backoff_seconds,
            )
            raw_markets = payload.get("markets", []) if isinstance(payload, dict) else []
            pages_fetched += 1

            for item in raw_markets:
                market = self._parse_market(item)
                if market is None or market.market_id in seen:
                    continue
                markets.append(market)
                seen.add(market.market_id)
                if target_limit is not None and len(markets) >= target_limit:
                    break

            after_cursor = payload.get("next_cursor") if isinstance(payload, dict) else None
            if not after_cursor or not raw_markets:
                break

        return markets

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
        outcomes = parse_jsonish(item.get("outcomes")) or []
        prices = parse_jsonish(item.get("outcomePrices")) or []
        token_ids = parse_jsonish(item.get("clobTokenIds")) or []

        if not isinstance(outcomes, list) or len(outcomes) < 2:
            return None

        outcome_map = {str(name).strip().lower(): idx for idx, name in enumerate(outcomes)}
        yes_idx = outcome_map.get("yes")
        no_idx = outcome_map.get("no")
        if yes_idx is None or no_idx is None:
            return None

        yes_mid = as_float(prices[yes_idx]) if yes_idx < len(prices) else None
        no_mid = as_float(prices[no_idx]) if no_idx < len(prices) else None
        best_bid = as_float(item.get("bestBid"))
        best_ask = as_float(item.get("bestAsk"))

        yes_bid = clamp_price(best_bid if best_bid is not None else yes_mid)
        yes_ask = clamp_price(best_ask if best_ask is not None else yes_mid)
        no_bid = clamp_price(no_mid)
        no_ask = clamp_price(no_mid)

        if no_bid is None and yes_ask is not None:
            no_bid = clamp_price(1.0 - yes_ask)
        if no_ask is None and yes_bid is not None:
            no_ask = clamp_price(1.0 - yes_bid)

        slug = item.get("slug")
        event = self._first_event(item)
        event_slug = self._event_slug(item, event)
        url = self._market_url(item, slug, event_slug)
        yes_token = token_ids[yes_idx] if isinstance(token_ids, list) and yes_idx < len(token_ids) else None
        no_token = token_ids[no_idx] if isinstance(token_ids, list) and no_idx < len(token_ids) else None
        tags = item.get("tags")

        return MarketSnapshot(
            venue="polymarket",
            market_id=str(item.get("conditionId") or item.get("id") or slug),
            question=str(item.get("question") or "").strip(),
            ticker=str(item.get("id")) if item.get("id") else None,
            slug=slug,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            no_bid=no_bid,
            no_ask=no_ask,
            liquidity=as_float(item.get("liquidityNum") or item.get("liquidityClob") or item.get("liquidity")),
            volume_24h=as_float(item.get("volume24hr") or item.get("volume24hrClob")),
            close_time=item.get("endDateIso") or item.get("endDate"),
            rules=item.get("description") or item.get("resolutionSource"),
            url=url,
            metadata={
                "category": item.get("category"),
                "tags": self._compact_tags(tags),
                "event_slug": event_slug,
                "event_title": event.get("title") if event else None,
                "event_ticker": event.get("ticker") if event else None,
                "yes_token_id": yes_token,
                "no_token_id": no_token,
            },
        )

    def _first_event(self, item: dict[str, Any]) -> dict[str, Any] | None:
        events = item.get("events")
        if isinstance(events, list) and events and isinstance(events[0], dict):
            return events[0]
        return None

    def _event_slug(self, item: dict[str, Any], event: dict[str, Any] | None) -> str | None:
        event_slug = item.get("eventSlug") or item.get("event_slug")
        if not event_slug and event:
            event_slug = event.get("slug")
        return str(event_slug) if event_slug else None

    def _compact_tags(self, tags: Any) -> list[str]:
        if not isinstance(tags, list):
            return []
        compact: list[str] = []
        for tag in tags[:8]:
            if isinstance(tag, dict):
                value = tag.get("label") or tag.get("name") or tag.get("slug")
            else:
                value = tag
            if value:
                compact.append(str(value))
        return compact

    def _market_url(
        self,
        item: dict[str, Any],
        market_slug: str | None,
        event_slug: str | None = None,
    ) -> str | None:
        if item.get("url"):
            return str(item["url"])
        if not market_slug:
            return None

        if event_slug and event_slug != market_slug:
            return f"https://polymarket.com/event/{event_slug}/{market_slug}"
        return f"https://polymarket.com/event/{market_slug}"

    async def _hydrate_orderbooks(
        self,
        client: httpx.AsyncClient,
        markets: list[MarketSnapshot],
        max_concurrent_requests: int,
        retry_attempts: int,
        retry_backoff_seconds: float,
    ) -> None:
        semaphore = asyncio.Semaphore(max_concurrent_requests)

        async def hydrate_side(market: MarketSnapshot, token_id: str, side: str) -> None:
            async with semaphore:
                book = await self._fetch_book(client, token_id, retry_attempts, retry_backoff_seconds)
                self._apply_book(market, book, side)

        tasks: list[asyncio.Task[None]] = []
        for market in markets:
            yes_token = market.metadata.get("yes_token_id")
            no_token = market.metadata.get("no_token_id")
            if yes_token:
                tasks.append(asyncio.create_task(hydrate_side(market, str(yes_token), "yes")))
            if no_token:
                tasks.append(asyncio.create_task(hydrate_side(market, str(no_token), "no")))

        if tasks:
            await asyncio.gather(*tasks)

    async def _fetch_book(
        self,
        client: httpx.AsyncClient,
        token_id: str,
        retry_attempts: int,
        retry_backoff_seconds: float,
    ) -> dict[str, Any] | None:
        try:
            return await self._get_json(
                client,
                f"{self.settings.polymarket_clob_base}/book",
                {"token_id": token_id},
                retry_attempts,
                retry_backoff_seconds,
            )
        except httpx.HTTPStatusError:
            return None

    def _apply_book(self, market: MarketSnapshot, book: dict[str, Any] | None, side: str) -> None:
        if not book:
            return
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        best_bid = bids[0] if bids else {}
        best_ask = asks[0] if asks else {}
        bid_price = clamp_price(as_float(best_bid.get("price")))
        ask_price = clamp_price(as_float(best_ask.get("price")))
        bid_size = as_float(best_bid.get("size"))
        ask_size = as_float(best_ask.get("size"))

        if side == "yes":
            market.yes_bid = bid_price
            market.yes_ask = ask_price
            market.yes_bid_size = bid_size
            market.yes_ask_size = ask_size
        else:
            market.no_bid = bid_price
            market.no_ask = ask_price
            market.no_bid_size = bid_size
            market.no_ask_size = ask_size
