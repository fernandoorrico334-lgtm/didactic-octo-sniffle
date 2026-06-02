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


def test_manual_pair_can_match_by_question_contains() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="condition-1",
        question="Will SpaceX launch Starship before July 2026?",
    )
    kalshi = MarketSnapshot(
        venue="kalshi",
        market_id="KXSTARSHIP",
        ticker="KXSTARSHIP",
        question="Will Starship launch before Jul 2026?",
    )

    pairs = match_markets(
        [poly],
        [kalshi],
        min_confidence=0.99,
        manual_specs=[
            {
                "id": "manual-question-contains",
                "polymarket_question_contains": "SpaceX launch Starship",
                "kalshi_question_contains": "Starship launch",
                "confidence": 0.96,
            }
        ],
    )

    assert len(pairs) == 1
    assert pairs[0].pair_id == "manual-question-contains"


def test_blocked_matching_finds_equivalent_market_among_noise() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="poly-fed",
        question="Will the Fed cut interest rates by June 2026?",
        close_time="2026-06-30T00:00:00Z",
        metadata={"category": "economy", "event_title": "Fed interest rates"},
    )
    kalshi_noise = [
        MarketSnapshot(
            venue="kalshi",
            market_id=f"KXNOISE-{idx}",
            ticker=f"KXNOISE-{idx}",
            question=f"Unrelated sports market {idx}",
            close_time="2026-06-30T00:00:00Z",
            metadata={"category": "sports"},
        )
        for idx in range(25)
    ]
    kalshi_match = MarketSnapshot(
        venue="kalshi",
        market_id="KXFEDCUT-26JUN",
        ticker="KXFEDCUT-26JUN",
        question="Will the Federal Reserve cut rates by June 2026?",
        close_time="2026-06-30T00:00:00Z",
        metadata={"category": "economy", "event_ticker": "KXFEDCUT"},
    )

    pairs = match_markets(
        [poly],
        [*kalshi_noise, kalshi_match],
        min_confidence=0.58,
        candidate_limit_per_market=5,
    )

    assert len(pairs) == 1
    assert pairs[0].kalshi.market_id == "KXFEDCUT-26JUN"


def test_confidence_penalizes_same_topic_with_different_dates() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="poly-rain-june",
        question="Will it rain in New York City on June 1, 2026?",
        close_time="2026-06-01T23:59:00Z",
    )
    kalshi = MarketSnapshot(
        venue="kalshi",
        market_id="KXRAINNYC-26JUN02",
        ticker="KXRAINNYC-26JUN02",
        question="Rain in New York City on Jun 2, 2026?",
        close_time="2026-06-02T23:59:00Z",
    )

    assert confidence_score(poly, kalshi) < 0.58

