from app.models import MarketSnapshot
from app.services.matcher import confidence_score, match_markets


def test_confidence_rewards_shared_numbers() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="poly-1",
        question="Will Bitcoin reach $100,000 before July 1, 2026?",
        close_time="2026-07-01T00:00:00Z",
    )
    kalshi = MarketSnapshot(
        venue="kalshi",
        market_id="kalshi-1",
        question="Will Bitcoin hit 100000 before Jul 1 2026?",
        close_time="2026-07-01T00:00:00Z",
    )

    assert confidence_score(poly, kalshi) > 0.58


def test_manual_pair_overrides_fuzzy_threshold() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="condition-1",
        slug="poly-slug",
        question="Completely different wording",
    )
    kalshi = MarketSnapshot(
        venue="kalshi",
        market_id="KXTEST",
        ticker="KXTEST",
        question="Another title",
    )

    pairs = match_markets(
        [poly],
        [kalshi],
        min_confidence=0.99,
        manual_specs=[
            {
                "id": "manual-1",
                "polymarket_slug": "poly-slug",
                "kalshi_ticker": "KXTEST",
                "confidence": 0.97,
            }
        ],
    )

    assert len(pairs) == 1
    assert pairs[0].pair_id == "manual-1"
    assert pairs[0].match_reason == "manual"

