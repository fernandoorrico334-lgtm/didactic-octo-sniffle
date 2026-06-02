from __future__ import annotations

from app.models import ArbitrageSignal, MarketPair, MarketSnapshot, SignalLeg, utc_now_iso
from app.settings import ScannerSettings
from app.utils import slugify


def _fee_for(price: float, fee_bps: float) -> float:
    return price * (fee_bps / 10_000.0)


def _ask_size(market: MarketSnapshot, side: str, fallback: float) -> float:
    size = market.yes_ask_size if side == "yes" else market.no_ask_size
    if size is None or size <= 0:
        return fallback
    return size


def _fee_bps(market: MarketSnapshot, settings: ScannerSettings) -> float:
    if market.venue == "polymarket":
        return settings.polymarket_fee_bps
    if market.venue == "kalshi":
        return settings.kalshi_fee_bps
    return 0.0


def _decimal_odds(price: float) -> float | None:
    if price <= 0:
        return None
    return round(1.0 / price, 4)


def _metadata_text(market: MarketSnapshot) -> str:
    raw = market.metadata.get("raw")
    category = market.metadata.get("category")
    tags = market.metadata.get("tags")
    parts = [market.question, market.ticker, market.slug, category]
    if isinstance(tags, list):
        parts.extend(str(tag.get("label") or tag.get("name") or tag.get("slug") or tag) for tag in tags)
    elif tags:
        parts.append(str(tags))
    if isinstance(raw, dict):
        for key in ("category", "series_ticker", "event_ticker", "title", "subtitle"):
            if raw.get(key):
                parts.append(str(raw[key]))
    return " ".join(str(part).lower() for part in parts if part)


def _category_for_pair(pair: MarketPair) -> str:
    text = f"{_metadata_text(pair.polymarket)} {_metadata_text(pair.kalshi)}"
    category_words = {
        "cripto": (
            "bitcoin",
            "btc",
            "ethereum",
            "eth",
            "crypto",
            "solana",
            "xrp",
            "dogecoin",
        ),
        "clima": (
            "weather",
            "rain",
            "snow",
            "temperature",
            "hurricane",
            "storm",
            "climate",
            "precipitation",
        ),
        "esportes": (
            "sport",
            "sports",
            "soccer",
            "football",
            "nba",
            "nfl",
            "mlb",
            "nhl",
            "ufc",
            "fifa",
            "tennis",
            "golf",
        ),
        "politica": (
            "election",
            "president",
            "senate",
            "congress",
            "house",
            "trump",
            "biden",
            "vote",
            "politic",
            "minister",
            "governor",
        ),
        "economia": (
            "fed",
            "rate",
            "inflation",
            "cpi",
            "gdp",
            "recession",
            "unemployment",
            "economy",
            "economic",
            "stocks",
            "market",
            "oil",
            "gold",
            "tariff",
        ),
    }
    for category, words in category_words.items():
        if any(word in text for word in words):
            return category
    return "outros"


def _leg(market: MarketSnapshot, side: str, price: float, size: float) -> SignalLeg:
    return SignalLeg(
        venue=market.venue,
        market_id=market.display_id,
        side=side,
        price=price,
        size=size,
        url=market.url,
    )


def _market_title(pair: MarketPair) -> str:
    poly_question = pair.polymarket.question.strip()
    kalshi_question = pair.kalshi.question.strip()
    return poly_question or kalshi_question or pair.pair_id


def _signal_for_direction(
    pair: MarketPair,
    yes_market: MarketSnapshot,
    no_market: MarketSnapshot,
    settings: ScannerSettings,
) -> ArbitrageSignal | None:
    yes_ask = yes_market.yes_ask
    no_ask = no_market.no_ask
    if yes_ask is None or no_ask is None:
        return None

    gross_edge = 1.0 - (yes_ask + no_ask)
    fees = _fee_for(yes_ask, _fee_bps(yes_market, settings)) + _fee_for(no_ask, _fee_bps(no_market, settings))
    net_edge = gross_edge - fees
    if net_edge < settings.min_net_edge:
        return None
    cost_per_contract = yes_ask + no_ask + fees

    max_size = min(
        settings.max_position_size,
        _ask_size(yes_market, "yes", settings.unknown_liquidity_size),
        _ask_size(no_market, "no", settings.unknown_liquidity_size),
    )
    estimated_profit = net_edge * max_size
    direction = f"buy-yes-{yes_market.venue}-buy-no-{no_market.venue}"
    warnings: list[str] = []
    if pair.confidence < 0.85:
        warnings.append("Low/medium market-match confidence. Review rules before trading.")
    if pair.resolution_notes:
        warnings.append(pair.resolution_notes)

    return ArbitrageSignal(
        signal_id=f"{slugify(direction)}-{pair.pair_id}",
        pair_id=pair.pair_id,
        direction=direction,
        buy_yes_venue=yes_market.venue,
        buy_no_venue=no_market.venue,
        market_title=_market_title(pair),
        yes_ask=yes_ask,
        no_ask=no_ask,
        gross_edge=round(gross_edge, 6),
        estimated_fees=round(fees, 6),
        net_edge=round(net_edge, 6),
        max_size=round(max_size, 4),
        estimated_profit=round(estimated_profit, 4),
        confidence=pair.confidence,
        created_at=utc_now_iso(),
        legs=[
            _leg(yes_market, "yes", yes_ask, max_size),
            _leg(no_market, "no", no_ask, max_size),
        ],
        warnings=warnings,
        category=_category_for_pair(pair),
        yes_decimal_odds=_decimal_odds(yes_ask),
        no_decimal_odds=_decimal_odds(no_ask),
        cost_per_contract=round(cost_per_contract, 6),
        max_total_stake=round(cost_per_contract * max_size, 4),
    )


def find_arbitrage_signals(pairs: list[MarketPair], settings: ScannerSettings) -> list[ArbitrageSignal]:
    signals: list[ArbitrageSignal] = []
    for pair in pairs:
        poly_yes_kalshi_no = _signal_for_direction(pair, pair.polymarket, pair.kalshi, settings)
        kalshi_yes_poly_no = _signal_for_direction(pair, pair.kalshi, pair.polymarket, settings)
        if poly_yes_kalshi_no:
            signals.append(poly_yes_kalshi_no)
        if kalshi_yes_poly_no:
            signals.append(kalshi_yes_poly_no)

    signals.sort(key=lambda signal: signal.net_edge, reverse=True)
    return signals[: settings.signal_limit]
