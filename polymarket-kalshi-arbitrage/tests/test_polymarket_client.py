import asyncio

from app.clients.polymarket import PolymarketClient
from app.settings import ApiSettings


def _market_payload(condition_id: str, slug: str) -> dict:
    return {
        "conditionId": condition_id,
        "question": f"Question {condition_id}",
        "slug": slug,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.40", "0.60"]',
        "active": True,
        "closed": False,
    }


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.pages = [
            {
                "markets": [_market_payload("condition-1", "market-one")],
                "next_cursor": "cursor-1",
            },
            {
                "markets": [_market_payload("condition-2", "market-two")],
                "next_cursor": "",
            },
        ]

    async def get(self, _url: str, params: dict) -> FakeResponse:
        self.calls.append(params)
        return FakeResponse(self.pages[len(self.calls) - 1])


class RetryFakeClient:
    def __init__(self) -> None:
        self.calls = 0

    async def get(self, _url: str, params: dict) -> FakeResponse:
        self.calls += 1
        if self.calls == 1:
            return FakeResponse({}, status_code=429)
        return FakeResponse({"markets": [_market_payload("condition-1", "market-one")], "next_cursor": ""})


def test_polymarket_keyset_fetches_all_pages_until_cursor_empty() -> None:
    client = PolymarketClient(ApiSettings())
    fake_client = FakeClient()

    markets = asyncio.run(
        client._fetch_keyset_markets(
            fake_client,
            target_limit=None,
            page_size=1,
            max_pages=10,
        )
    )

    assert [market.market_id for market in markets] == ["condition-1", "condition-2"]
    assert fake_client.calls[0]["limit"] == "1"
    assert fake_client.calls[1]["after_cursor"] == "cursor-1"


def test_polymarket_url_uses_event_and_market_slug_when_available() -> None:
    client = PolymarketClient(ApiSettings())
    market = client._parse_market(
        {
            **_market_payload("condition-1", "fed-rate-cut-by-june-2026-meeting"),
            "events": [{"slug": "fed-rate-cut-by-629"}],
        }
    )

    assert market is not None
    assert market.url == "https://polymarket.com/event/fed-rate-cut-by-629/fed-rate-cut-by-june-2026-meeting"


def test_polymarket_retries_after_rate_limit_response() -> None:
    client = PolymarketClient(ApiSettings())
    fake_client = RetryFakeClient()

    markets = asyncio.run(
        client._fetch_keyset_markets(
            fake_client,
            target_limit=None,
            page_size=1,
            max_pages=1,
            retry_attempts=1,
            retry_backoff_seconds=0,
        )
    )

    assert fake_client.calls == 2
    assert [market.market_id for market in markets] == ["condition-1"]
