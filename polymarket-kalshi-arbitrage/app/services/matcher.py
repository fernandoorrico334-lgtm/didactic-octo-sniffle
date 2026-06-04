from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
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
    "what",
    "when",
    "where",
    "who",
    "which",
    "if",
    "any",
    "named",
    "individual",
    "wins",
    "win",
    "resolve",
    "resolution",
}


TOKEN_ALIASES = {
    "btc": {"bitcoin"},
    "bitcoin": {"btc"},
    "eth": {"ethereum"},
    "ethereum": {"eth"},
    "temperature": {"temp"},
    "temp": {"temperature"},
    "fed": {"federal", "reserve"},
    "federal": {"fed"},
    "rates": {"rate"},
    "rainfall": {"rain"},
    "raining": {"rain"},
    "precipitation": {"rain"},
    "nyc": {"new", "york"},
    "nba": {"basketball"},
    "basketball": {"nba"},
    "knicks": {"new", "york"},
    "spurs": {"san", "antonio"},
    "jan": {"january"},
    "feb": {"february"},
    "mar": {"march"},
    "apr": {"april"},
    "jun": {"june"},
    "jul": {"july"},
    "aug": {"august"},
    "sep": {"september"},
    "sept": {"september"},
    "oct": {"october"},
    "nov": {"november"},
    "dec": {"december"},
}


MONTHS = {
    "jan": "01",
    "january": "01",
    "feb": "02",
    "february": "02",
    "mar": "03",
    "march": "03",
    "apr": "04",
    "april": "04",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "aug": "08",
    "august": "08",
    "sep": "09",
    "sept": "09",
    "september": "09",
    "oct": "10",
    "october": "10",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}


ASSET_ALIASES = {
    "btc": {"btc", "bitcoin"},
    "eth": {"eth", "ethereum"},
}


CITY_ALIASES = {
    "new-york-city": {"new york city", "nyc", "new york"},
    "chicago": {"chicago"},
    "los-angeles": {"los angeles", "la"},
    "miami": {"miami"},
}


LEAGUE_ALIASES = {
    "nba": {"nba", "pro basketball"},
    "nfl": {"nfl", "pro football"},
    "mlb": {"mlb", "pro baseball"},
    "nhl": {"nhl", "pro hockey"},
    "fifa-world-cup": {"fifa world cup", "world cup"},
}


TEAM_ALIASES = {
    "new-york-knicks": {"new york knicks", "knicks"},
    "san-antonio-spurs": {"san antonio spurs", "spurs"},
    "boston-red-sox": {"boston red sox", "boston"},
    "new-york-yankees": {"new york yankees", "new york y", "yankees"},
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
    expanded: set[str] = set()
    for token in tokens:
        if len(token) <= 1:
            continue
        expanded.add(token)
        expanded.update(TOKEN_ALIASES.get(token, set()))
    return expanded


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


def _metadata_text(market: MarketSnapshot) -> str:
    parts = [
        market.ticker,
        market.slug,
        market.metadata.get("category"),
        market.metadata.get("event_ticker"),
        market.metadata.get("event_slug"),
        market.metadata.get("event_title"),
        market.metadata.get("series_ticker"),
        market.metadata.get("title"),
        market.metadata.get("subtitle"),
        market.metadata.get("yes_sub_title"),
    ]
    tags = market.metadata.get("tags")
    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags)
    return " ".join(str(part) for part in parts if part)


def _full_market_text(market: MarketSnapshot) -> str:
    return " ".join(
        str(part)
        for part in (
            market.question,
            market.ticker,
            market.slug,
            _metadata_text(market),
            market.rules,
        )
        if part
    )


def _contains_alias(text: str, aliases: set[str]) -> bool:
    normalized = normalize_text(text)
    padded = f" {normalized} "
    return any(f" {normalize_text(alias)} " in padded for alias in aliases)


def _find_alias_key(text: str, alias_map: dict[str, set[str]]) -> str | None:
    for key, aliases in alias_map.items():
        if _contains_alias(text, aliases):
            return key
    return None


def _year_markers(text: str, close_time: str | None) -> set[str]:
    years = set(re.findall(r"\b20\d{2}\b", text))
    if close_time and len(close_time) >= 4:
        years.add(close_time[:4])
    return years


def _date_markers(text: str, close_time: str | None) -> set[str]:
    normalized = normalize_text(text)
    dates: set[str] = set()
    if close_time:
        dates.add(close_time[:10])

    for month, day, year in re.findall(
        r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+(20\d{2})\b",
        normalized,
    ):
        dates.add(f"{year}-{MONTHS[month]}-{int(day):02d}")

    fallback_year = close_time[:4] if close_time else None
    if fallback_year:
        for month, day in re.findall(
            r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b",
            normalized,
        ):
            dates.add(f"{fallback_year}-{MONTHS[month]}-{int(day):02d}")
    return dates


def _scaled_amount(raw_value: str, suffix: str = "") -> float:
    value = float(raw_value)
    suffix = suffix.lower()
    if suffix == "k":
        value *= 1_000
    elif suffix == "m":
        value *= 1_000_000
    elif suffix == "b":
        value *= 1_000_000_000
    return value


def _contextual_thresholds(text: str, kind: str) -> set[float]:
    normalized = normalize_text(text)
    amounts: set[float] = set()
    if kind == "crypto-price":
        for raw_value, suffix in re.findall(
            r"(?:\$|above|below|under|over|hit|hits|reach|reaches|reached)\s*\$?(\d+(?:\.\d+)?)(k|m|b)?\b",
            normalized,
        ):
            amounts.add(_scaled_amount(raw_value, suffix))
        for raw_value, suffix in re.findall(r"\$(\d+(?:\.\d+)?)(k|m|b)?\b", normalized):
            amounts.add(_scaled_amount(raw_value, suffix))
        return amounts

    if kind == "weather-temp":
        for raw_value in re.findall(r"(?:above|below|under|over)\s+(-?\d+(?:\.\d+)?)", normalized):
            amounts.add(float(raw_value))
        for raw_value in re.findall(r"(-?\d+(?:\.\d+)?)\s*(?:°|degrees?)", normalized):
            amounts.add(float(raw_value))
        return amounts

    for raw_value, suffix in re.findall(r"\$?\b(\d+(?:\.\d+)?)(k|m|b)?\b", normalized):
        value = float(raw_value)
        if suffix:
            value = _scaled_amount(raw_value, suffix)
        elif value.is_integer() and 2020 <= int(value) <= 2035:
            continue
        amounts.add(value)
    return amounts


def _threshold_key(value: float) -> str:
    if abs(value - round(value)) <= 0.02:
        return str(int(round(value)))
    if abs(value - (math.floor(value) + 0.99)) <= 0.021:
        return str(int(math.ceil(value)))
    if value >= 1_000:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _market_kinds(text: str) -> set[str]:
    normalized = normalize_text(text)
    kinds: set[str] = set()
    if "golden boot" in normalized and ("cleat" in normalized or "branded" in normalized):
        kinds.add("worldcup-cleats")
    if "first goalscorer" in normalized:
        kinds.add("first-goalscorer")
    if "road win" in normalized:
        kinds.add("series-road-wins")
    if "extra inning" in normalized:
        kinds.add("extra-innings")
    if "fewest goals" in normalized or "most goals" in normalized:
        kinds.add("group-stage-goals")
    if "temperature" in normalized or re.search(r"\btemp\b", normalized):
        kinds.add("weather-temp")
    if re.search(r"\brain\b", normalized):
        kinds.add("weather-rain")
    if ("bitcoin" in normalized or re.search(r"\bbtc\b", normalized)) and not (
        "truflation" in normalized or "purchasing power" in normalized
    ):
        if any(word in normalized for word in ("price", "hit", "reach", "above", "below", "under")):
            kinds.add("crypto-price")
    if any(_contains_alias(normalized, aliases) for aliases in LEAGUE_ALIASES.values()):
        if any(word in normalized for word in ("champion", "finals", "win")):
            kinds.add("sports-champion")
        if "winner" in normalized:
            kinds.add("sports-game-winner")
    if "presidential nomination" in normalized:
        kinds.add("election-nomination")
    elif "election" in normalized or "governor race" in normalized or "senate" in normalized:
        kinds.add("election-winner")
    return kinds


def _kind_conflict(left: set[str], right: set[str]) -> bool:
    if not left or not right or left & right:
        return False
    sports = {
        "sports-champion",
        "sports-game-winner",
        "worldcup-cleats",
        "first-goalscorer",
        "series-road-wins",
        "extra-innings",
        "group-stage-goals",
    }
    weather = {"weather-temp", "weather-rain"}
    crypto = {"crypto-price"}
    politics = {"election-nomination", "election-winner"}
    return any(left & group and right & group for group in (sports, weather, crypto, politics))


def _contract_keys(market: MarketSnapshot) -> set[str]:
    text = _full_market_text(market)
    normalized = normalize_text(text)
    keys: set[str] = set()
    dates = _date_markers(normalized, market.close_time)
    years = _year_markers(normalized, market.close_time)
    kinds = _market_kinds(normalized)

    asset = _find_alias_key(normalized, ASSET_ALIASES)
    if asset and "crypto-price" in kinds:
        thresholds = {_threshold_key(value) for value in _contextual_thresholds(normalized, "crypto-price")}
        for threshold in thresholds:
            for date in dates or years:
                keys.add(f"crypto-price:{asset}:{threshold}:{date}")

    city = _find_alias_key(normalized, CITY_ALIASES)
    if city and "weather-temp" in kinds:
        thresholds = {_threshold_key(value) for value in _contextual_thresholds(normalized, "weather-temp")}
        for threshold in thresholds:
            for date in dates:
                keys.add(f"weather-temp:{city}:{threshold}:{date}")
    if city and "weather-rain" in kinds:
        for date in dates:
            keys.add(f"weather-rain:{city}:{date}")

    league = _find_alias_key(normalized, LEAGUE_ALIASES)
    team = _find_alias_key(normalized, TEAM_ALIASES)
    if league and team and "sports-champion" in kinds:
        for year in years:
            keys.add(f"sports-champion:{league}:{team}:{year}")

    return keys


def _category_value(market: MarketSnapshot) -> str | None:
    raw = market.metadata.get("category")
    if not raw:
        return None
    return normalize_text(str(raw)).replace(" ", "-")


def _market_features(market: MarketSnapshot) -> dict[str, Any]:
    metadata_text = _metadata_text(market)
    full_text = _full_market_text(market)
    searchable_text = f"{market.question} {metadata_text}"
    rules_text = (market.rules or "")[:600]
    return {
        "question_tokens": tokenize(market.question),
        "search_tokens": tokenize(searchable_text),
        "rules_tokens": tokenize(rules_text),
        "numbers": extract_numbers(searchable_text),
        "close_date": market.close_time[:10] if market.close_time else None,
        "category": _category_value(market),
        "contract_keys": _contract_keys(market),
        "kinds": _market_kinds(full_text),
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


def _category_score_from_features(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_category = left["category"]
    right_category = right["category"]
    if not left_category or not right_category:
        return 0.5
    return 1.0 if left_category == right_category else 0.0


def _confidence_from_features(left: dict[str, Any], right: dict[str, Any]) -> float:
    words = _set_overlap_score(left["question_tokens"], right["question_tokens"], empty_score=0.0)
    search = _set_overlap_score(left["search_tokens"], right["search_tokens"], empty_score=0.0)
    rules = _set_overlap_score(left["rules_tokens"], right["rules_tokens"], empty_score=0.5)
    nums = _set_overlap_score(left["numbers"], right["numbers"], empty_score=1.0)
    times = _time_score_from_features(left, right)
    category = _category_score_from_features(left, right)
    score = (0.46 * words) + (0.20 * search) + (0.06 * rules) + (0.16 * nums) + (0.09 * times) + (0.03 * category)
    if left["contract_keys"] & right["contract_keys"]:
        score = max(score, 0.94)
    if _kind_conflict(left["kinds"], right["kinds"]):
        score = min(score * 0.45, 0.35)
    if left["close_date"] and right["close_date"] and left["close_date"] != right["close_date"] and nums < 0.5:
        score *= 0.75
    return round(score, 4)


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


def _flatten_identifiers(*identifiers: Any) -> list[str]:
    flattened: list[str] = []
    for identifier in identifiers:
        if isinstance(identifier, list):
            flattened.extend(str(item) for item in identifier if item)
        elif identifier:
            flattened.append(str(identifier))
    return flattened


def _matches_identifier(market: MarketSnapshot, *identifiers: Any) -> bool:
    ids = {market.market_id, market.ticker, market.slug, slugify(market.question)}
    clean_ids = {item for item in ids if item}
    return any(identifier in clean_ids for identifier in _flatten_identifiers(*identifiers))


def _matches_contains(market: MarketSnapshot, *needles: Any) -> bool:
    values = _flatten_identifiers(*needles)
    if not values:
        return False
    haystack = normalize_text(f"{market.question} {_metadata_text(market)}")
    return any(normalize_text(value) in haystack for value in values)


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
                or _matches_contains(market, spec.get("polymarket_question_contains"))
            ),
            None,
        )
        kalshi = next(
            (
                market
                for market in kalshis
                if _matches_identifier(market, spec.get("kalshi_ticker"), spec.get("kalshi_id"))
                or _matches_contains(market, spec.get("kalshi_question_contains"))
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


def _is_specific_number(value: str) -> bool:
    if value.isdigit() and 2020 <= int(value) <= 2035:
        return False
    return len(value.replace(".", "")) >= 3


def _blocking_keys(features: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for contract_key in features["contract_keys"]:
        keys.add(f"s:{contract_key}")
    for token in features["question_tokens"] | features["search_tokens"]:
        if len(token) >= 3 and not token.isdigit():
            keys.add(f"t:{token}")
    for number in features["numbers"]:
        if _is_specific_number(number):
            keys.add(f"n:{number}")
    if features["close_date"]:
        keys.add(f"d:{features['close_date']}")
    if features["category"]:
        keys.add(f"c:{features['category']}")
    return keys


def _candidate_indexes_for_market(
    features: dict[str, Any],
    index: dict[str, list[int]],
    *,
    max_bucket_size: int = 600,
) -> set[int]:
    candidates: set[int] = set()
    for key in _blocking_keys(features):
        bucket = index.get(key, [])
        if bucket and len(bucket) <= max_bucket_size:
            candidates.update(bucket)
    return candidates


def match_markets(
    polymarkets: list[MarketSnapshot],
    kalshis: list[MarketSnapshot],
    min_confidence: float,
    manual_specs: list[dict[str, Any]] | None = None,
    candidate_limit_per_market: int = 80,
    max_auto_pairs: int = 500,
) -> list[MarketPair]:
    manual_specs = manual_specs or []
    pairs = _manual_pairs(polymarkets, kalshis, manual_specs)
    manual_pair_count = len(pairs)
    used_poly = {pair.polymarket.market_id for pair in pairs}
    used_kalshi = {pair.kalshi.market_id for pair in pairs}

    candidates: list[tuple[float, MarketSnapshot, MarketSnapshot]] = []
    poly_features = [(market, _market_features(market)) for market in polymarkets if market.market_id not in used_poly]
    kalshi_features = [(market, _market_features(market)) for market in kalshis if market.market_id not in used_kalshi]

    kalshi_index: dict[str, list[int]] = defaultdict(list)
    for idx, (_market, feature) in enumerate(kalshi_features):
        for key in _blocking_keys(feature):
            kalshi_index[key].append(idx)

    for poly, poly_feature in poly_features:
        candidate_indexes = _candidate_indexes_for_market(poly_feature, kalshi_index)
        if not candidate_indexes and len(kalshi_features) <= 500:
            candidate_indexes = set(range(len(kalshi_features)))

        scored_for_poly: list[tuple[float, MarketSnapshot, MarketSnapshot]] = []
        for idx in candidate_indexes:
            kalshi, kalshi_feature = kalshi_features[idx]
            score = _confidence_from_features(poly_feature, kalshi_feature)
            if score >= min_confidence:
                scored_for_poly.append((score, poly, kalshi))
        scored_for_poly.sort(key=lambda item: item[0], reverse=True)
        candidates.extend(scored_for_poly[: max(1, candidate_limit_per_market)])

    candidates.sort(key=lambda item: item[0], reverse=True)
    for score, poly, kalshi in candidates:
        if max_auto_pairs > 0 and len(pairs) >= manual_pair_count + max_auto_pairs:
            break
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
