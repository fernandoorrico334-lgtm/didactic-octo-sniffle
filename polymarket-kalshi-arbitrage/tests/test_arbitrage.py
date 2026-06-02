from app.models import MarketPair, MarketSnapshot
from app.services.arbitrage import find_arbitrage_signals
from app.settings import ScannerSettings


def test_detects_cross_venue_yes_no_arbitrage() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="poly-1",
        question="Will BTC hit 100k?",
        yes_ask=0.60,
        no_ask=0.42,
        yes_ask_size=10,
        no_ask_size=10,
    )
    kalshi = MarketSnapshot(
        venue="kalshi",
        market_id="kalshi-1",
        question="Will BTC hit 100k?",
        yes_ask=0.64,
        no_ask=0.36,
        yes_ask_size=10,
        no_ask_size=10,
    )
    pair = MarketPair("pair-1", poly, kalshi, 0.95, "manual")
    settings = ScannerSettings(min_net_edge=0.01, max_position_size=10)

    signals = find_arbitrage_signals([pair], settings)

    assert len(signals) == 1
    assert signals[0].direction == "buy-yes-polymarket-buy-no-kalshi"
    assert signals[0].net_edge == 0.04
    assert signals[0].estimated_profit == 0.4
    assert signals[0].market_title == "Will BTC hit 100k?"
    assert signals[0].yes_decimal_odds == 1.6667
    assert signals[0].no_decimal_odds == 2.7778
    assert signals[0].cost_per_contract == 0.96
    assert signals[0].max_total_stake == 9.6
    assert signals[0].category == "cripto"


def test_ignores_edges_below_threshold_after_fees() -> None:
    poly = MarketSnapshot(
        venue="polymarket",
        market_id="poly-1",
        question="Will BTC hit 100k?",
        yes_ask=0.60,
        no_ask=0.41,
    )
    kalshi = MarketSnapshot(
        venue="kalshi",
        market_id="kalshi-1",
        question="Will BTC hit 100k?",
        yes_ask=0.61,
        no_ask=0.395,
    )
    pair = MarketPair("pair-1", poly, kalshi, 0.95, "manual")
    settings = ScannerSettings(min_net_edge=0.01, polymarket_fee_bps=10, kalshi_fee_bps=10)

    signals = find_arbitrage_signals([pair], settings)

    assert signals == []
