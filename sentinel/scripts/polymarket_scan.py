#!/usr/bin/env python3
"""
polymarket_scan.py — Scan Polymarket Gamma API for macro-relevant prediction markets.

Queries active markets, filters by macro keywords, classifies risk signal.

Output JSON to stdout. Logging to stderr.
"""

import json
import logging
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.trading"))

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [polymarket_scan] %(levelname)s %(message)s",
)
log = logging.getLogger("polymarket_scan")

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"

# Macro-relevant keywords (case-insensitive)
MACRO_KEYWORDS = [
    "fed", "fomc", "rate", "cpi", "inflation", "recession",
    "spx", "s&p", "market", "crash", "powell",
]

# Negative macro event keywords used to classify whether a market is bearish
NEGATIVE_EVENT_KEYWORDS = [
    "cut", "recession", "crash", "fall", "drop", "decline",
    "lower", "reduce", "below", "miss", "slowdown", "contraction",
]

# Thresholds
MEDIUM_THRESHOLD = 0.60  # >60% → medium risk
HIGH_THRESHOLD = 0.75    # >75% → high risk


def fetch_markets() -> list[dict]:
    """Fetch active, non-closed markets from Polymarket Gamma API."""
    params = {
        "active": "true",
        "closed": "false",
        "limit": 50,
    }
    log.info("Fetching markets from Polymarket Gamma API...")
    resp = requests.get(GAMMA_API_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    # API returns a list directly
    if isinstance(data, list):
        return data
    return data.get("markets", data.get("results", []))


def is_macro_relevant(question: str) -> bool:
    """Check if market question contains any macro keyword."""
    q_lower = question.lower()
    return any(kw in q_lower for kw in MACRO_KEYWORDS)


def is_negative_macro_event(question: str) -> bool:
    """Heuristic: does the question suggest a negative macro outcome?"""
    q_lower = question.lower()
    return any(kw in q_lower for kw in NEGATIVE_EVENT_KEYWORDS)


def parse_yes_probability(outcome_prices) -> float | None:
    """
    Parse outcomePrices field — can be a list of strings, a JSON string,
    or a dict. Returns the 'Yes' probability as a float.
    """
    if outcome_prices is None:
        return None

    # Already a list
    if isinstance(outcome_prices, list):
        prices = outcome_prices
    elif isinstance(outcome_prices, str):
        try:
            prices = json.loads(outcome_prices)
        except (json.JSONDecodeError, ValueError):
            return None
    else:
        return None

    # Polymarket typically returns [yes_price, no_price] as strings
    if len(prices) >= 1:
        try:
            return float(prices[0])
        except (ValueError, TypeError):
            return None
    return None


def classify_risk_signal(relevant_markets: list[dict]) -> str:
    """
    Classify macro risk signal based on relevant market probabilities.

    - high: any negative-event market >75% probability
    - medium: any negative-event market >60% probability
    - low: none of the above
    """
    for market in relevant_markets:
        prob = market.get("yes_probability")
        if prob is None:
            continue

        question = market.get("question", "")
        if is_negative_macro_event(question) and prob > HIGH_THRESHOLD:
            log.warning(f"HIGH risk signal: '{question}' at {prob:.1%}")
            return "high"

    for market in relevant_markets:
        prob = market.get("yes_probability")
        if prob is None:
            continue

        question = market.get("question", "")
        if is_negative_macro_event(question) and prob > MEDIUM_THRESHOLD:
            log.warning(f"MEDIUM risk signal: '{question}' at {prob:.1%}")
            return "medium"

    return "low"


def main():
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    try:
        all_markets = fetch_markets()
        log.info(f"Total markets fetched: {len(all_markets)}")

        relevant_markets = []
        for m in all_markets:
            question = m.get("question", "") or m.get("title", "") or ""
            if not is_macro_relevant(question):
                continue

            outcome_prices = m.get("outcomePrices") or m.get("outcome_prices")
            yes_prob = parse_yes_probability(outcome_prices)

            volume_raw = m.get("volume") or m.get("volumeNum") or 0
            try:
                volume = float(volume_raw)
            except (ValueError, TypeError):
                volume = 0.0

            relevant_markets.append({
                "question": question,
                "yes_probability": round(yes_prob, 4) if yes_prob is not None else None,
                "volume": round(volume, 2),
            })

        log.info(f"Relevant macro markets: {len(relevant_markets)}")

        macro_risk_signal = classify_risk_signal(relevant_markets)
        log.info(f"macro_risk_signal: {macro_risk_signal}")

        result = {
            "markets": relevant_markets,
            "macro_risk_signal": macro_risk_signal,
            "relevant_count": len(relevant_markets),
            "timestamp": timestamp,
        }
        print(json.dumps(result))

    except requests.RequestException as e:
        log.error(f"Polymarket API request failed: {e}")
        result = {
            "macro_risk_signal": "unknown",
            "error": f"API request failed: {e}",
            "markets": [],
            "timestamp": timestamp,
        }
        print(json.dumps(result))
        sys.exit(1)

    except Exception as e:
        log.error(f"Unexpected error: {e}", exc_info=True)
        result = {
            "macro_risk_signal": "unknown",
            "error": str(e),
            "markets": [],
            "timestamp": timestamp,
        }
        print(json.dumps(result))
        sys.exit(1)


if __name__ == "__main__":
    main()
