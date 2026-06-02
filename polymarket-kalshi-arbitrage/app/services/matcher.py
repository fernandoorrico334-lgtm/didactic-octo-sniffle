from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any

from app.models import MarketPair, MarketSnapshot
from app.utils import slugify


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "will",
    "with",
    "yes",
    "no",
    "market",
    "event",
    "before",
    "after",
}


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(r"[^a-z0-9\s./-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> set[str]:
    normalized = normalize_text(text)
    tokens = {token for token in normalized.split(" ") if token and token not in STOPWORDS}
    return {token for token in tokens if len(token) > 1}


def extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", normalize_text(text)))


def token_score(left: str, right: str) -> float:
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return len(intersection) / len(union)


def number_score(left: str, right: str) -> float:
    left_numbers = extract_numbers(left)
    right_numbers = extract_numbers(right)
    if not left_numbers and not right_numbers:
        return 1.0
    if not left_numbers or not right_numbers:
        return 0.0
    return len(left_numbers & right_numbers) / len(left_numbers | right_numbers)


def time_score(left: MarketSnapshot, right: MarketSnapshot) -> float:
    if not left.close_time or not right.close_time:
        return 0.5
    return 1.0 if left.close_time[:10] == right.close_time[:10] else 0.25


def _market_features(market: MarketSnapshot) -> dict[str, Any]:
    return {
        "tokens": tokenize(market.question),
        "numbers": extract_numbers(market.question),
        "close_date": market.close_time[:10] if market.close_time else None,
    }


def _set_overlap_score(left: set[str], right: set[str], *, empty_score: float) -> float:
    if not left and not right:
        return empty_score
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _time_score_from_features(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_date = left["close_date"]
    right_date = right["close_date"]
    if not left_date or not right_date:
        return 0.5
    return 1.0 if left_date == right_date else 0.25


def _confidence_from_features(left: dict[str, Any], right: dict[str, Any]) -> float:
    words = _set_overlap_score(left["tokens"], right["tokens"], empty_score=0.0)
    nums = _set_overlap_score(left["numbers"], right["numbers"], empty_score=1.0)
    times = _time_score_from_features(left, right)
    return round((0.70 * words) + (0.20 * nums) + (0.10 * times), 4)


def confidence_score(left: MarketSnapshot, right: MarketSnapshot) -> float:
    return _confidence_from_features(_market_features(left), _market_features(right))


def stable_pair_id(left: MarketSnapshot, right: MarketSnapshot) -> str:
    raw = f"{left.venue}:{left.display_id}|{right.venue}:{right.display_id}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"pair-{digest}"


def load_manual_pair_specs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise RuntimeError("PyYAML is required to load manual pair mappings.") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("pairs") or [])


def _matches_identifier(market: MarketSnapshot, *identifiers: str | None) -> bool:
    ids = {market.market_id, market.ticker, market.slug, slugify(market.question)}
    clean_ids = {item for item in ids if item}
    return any(identifier in clean_ids for identifier in identifiers if identifier)


def _manual_pairs(
    polymarkets: list[MarketSnapshot],
    kalshis: list[MarketSnapshot],
    specs: list[dict[str, Any]],
) -> list[MarketPair]:
    pairs: list[MarketPair] = []
    for spec in specs:
        poly = next(
            (
                market
                for market in polymarkets
                if _matches_identifier(market, spec.get("polymarket_id"), spec.get("polymarket_slug"))
            ),
            None,
        )
        kalshi = next(
            (
                market
                for market in kalshis
                if _matches_identifier(market, spec.get("kalshi_ticker"), spec.get("kalshi_id"))
            ),
            None,
        )
        if not poly or not kalshi:
            continue
        pairs.append(
            MarketPair(
                pair_id=str(spec.get("id") or stable_pair_id(poly, kalshi)),
                polymarket=poly,
                kalshi=kalshi,
                confidence=float(spec.get("confidence", 0.98)),
                match_reason="manual",
                resolution_notes=spec.get("resolution_notes"),
            )
        )
    return pairs


def match_markets(
    polymarkets: list[MarketSnapshot],
    kalshis: list[MarketSnapshot],
    min_confidence: float,
    manual_specs: list[dict[str, Any]] | None = None,
) -> list[MarketPair]:
    manual_specs = manual_specs or []
    pairs = _manual_pairs(polymarkets, kalshis, manual_specs)
    used_poly = {pair.polymarket.market_id for pair in pairs}
    used_kalshi = {pair.kalshi.market_id for pair in pairs}

    candidates: list[tuple[float, MarketSnapshot, MarketSnapshot]] = []
    poly_features = [(market, _market_features(market)) for market in polymarkets if market.market_id not in used_poly]
    kalshi_features = [(market, _market_features(market)) for market in kalshis if market.market_id not in used_kalshi]
    skip_disjoint_tokens = min_confidence > 0.3

    for poly, poly_feature in poly_features:
        for kalshi, kalshi_feature in kalshi_features:
            if skip_disjoint_tokens and not (poly_feature["tokens"] & kalshi_feature["tokens"]):
                continue
            score = _confidence_from_features(poly_feature, kalshi_feature)
            if score >= min_confidence:
                candidates.append((score, poly, kalshi))

    candidates.sort(key=lambda item: item[0], reverse=True)
    for score, poly, kalshi in candidates:
        if poly.market_id in used_poly or kalshi.market_id in used_kalshi:
            continue
        if math.isclose(score, 0.0):
            continue
        pairs.append(
            MarketPair(
                pair_id=stable_pair_id(poly, kalshi),
                polymarket=poly,
                kalshi=kalshi,
                confidence=score,
                match_reason="fuzzy-title",
            )
        )
        used_poly.add(poly.market_id)
        used_kalshi.add(kalshi.market_id)

    return pairs
