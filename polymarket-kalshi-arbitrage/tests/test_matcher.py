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


def test_contract_signature_matches_crypto_threshold_aliases() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="poly-btc-150",
        question="Will Bitcoin hit $150k by June 30, 2026?",
        close_time="2026-06-30T23:59:00Z",
    )
    kalshi = MarketSnapshot(
        venue="kalshi",
        market_id="KXBTC-26JUN30-T150000",
        ticker="KXBTC-26JUN30-T150000",
        question="Will BTC price be above 149999.99 on Jun 30, 2026?",
        close_time="2026-06-30T20:00:00Z",
    )

    pairs = match_markets([poly], [kalshi], min_confidence=0.58)

    assert len(pairs) == 1
    assert pairs[0].confidence >= 0.9


def test_contract_signature_matches_weather_threshold_rounding() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="poly-nyc-temp",
        question="Will the temperature in NYC be above 97 degrees on June 4, 2026?",
        close_time="2026-06-04T23:59:00Z",
    )
    kalshi = MarketSnapshot(
        venue="kalshi",
        market_id="KXTEMPNYCH-26JUN0415-T96.99",
        ticker="KXTEMPNYCH-26JUN0415-T96.99",
        question="Will the temp in New York City be above 96.99° on Jun 4, 2026 at 3pm EDT?",
        close_time="2026-06-04T19:00:00Z",
    )

    pairs = match_markets([poly], [kalshi], min_confidence=0.58)

    assert len(pairs) == 1
    assert pairs[0].confidence >= 0.9


def test_weather_signature_does_not_use_date_number_as_threshold() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="poly-nyc-temp-80",
        question="Will the temperature in NYC be above 80 degrees on June 4, 2026?",
        close_time="2026-06-04T23:59:00Z",
    )
    kalshi = MarketSnapshot(
        venue="kalshi",
        market_id="KXTEMPNYCH-26JUN0415-T96.99",
        ticker="KXTEMPNYCH-26JUN0415-T96.99",
        question="Will the temp in New York City be above 96.99° on Jun 4, 2026 at 3pm EDT?",
        close_time="2026-06-04T19:00:00Z",
    )

    assert match_markets([poly], [kalshi], min_confidence=0.58) == []


def test_contract_signature_matches_sports_champion_aliases() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="poly-knicks",
        question="Will the New York Knicks win the 2026 NBA Finals?",
        close_time="2026-07-01T00:00:00Z",
    )
    kalshi = MarketSnapshot(
        venue="kalshi",
        market_id="KXNBA-26CHAMP-NYK",
        ticker="KXNBA-26CHAMP-NYK",
        question="Will New York Knicks be the 2026 Pro Basketball champion?",
        close_time="2026-06-20T14:00:00Z",
    )

    pairs = match_markets([poly], [kalshi], min_confidence=0.58)

    assert len(pairs) == 1
    assert pairs[0].confidence >= 0.9


def test_kind_conflict_blocks_world_cup_false_positive() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="poly-senegal-world-cup",
        question="Will Senegal win the 2026 FIFA World Cup?",
        close_time="2026-07-20T00:00:00Z",
    )
    kalshi = MarketSnapshot(
        venue="kalshi",
        market_id="KXWORLDCUPCLEATS-PUMA",
        ticker="KXWORLDCUPCLEATS-PUMA",
        question="Will the Golden Boot winner wear Puma branded cleats during the 2026 FIFA Men's World Cup?",
        close_time="2026-07-20T03:59:00Z",
    )

    assert confidence_score(poly, kalshi) < 0.58
    assert match_markets([poly], [kalshi], min_confidence=0.58) == []

