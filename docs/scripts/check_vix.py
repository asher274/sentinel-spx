#!/usr/bin/env python3
"""
check_vix.py — Fetch VIX and classify volatility regime.

Primary source: FRED API (series VIXCLS)
Fallback: Polygon /v2/aggs/ticker/VIX/prev

Output JSON to stdout. Logging to stderr.
"""

import json
import logging
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

# Load env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.trading"))

# Logging to stderr
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [check_vix] %(levelname)s %(message)s",
)
log = logging.getLogger("check_vix")

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")


def classify_regime(vix: float) -> tuple[str, float, bool]:
    """Return (regime, size_multiplier, trading_allowed)."""
    if vix < 14:
        return "low", 1.0, True
    elif vix < 25:
        return "normal", 1.0, True
    elif vix < 30:
        return "elevated", 0.5, True
    else:
        return "extreme", 0.0, False


def fetch_vix_fred() -> float:
    """Fetch latest VIX close from FRED API."""
    if not FRED_API_KEY:
        raise ValueError("FRED_API_KEY not set")
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": "VIXCLS",
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 5,
    }
    log.info("Fetching VIX from FRED...")
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    observations = data.get("observations", [])
    # Find the most recent non-"." value
    for obs in observations:
        val = obs.get("value", ".")
        if val != ".":
            return float(val)
    raise ValueError("No valid VIX observations returned from FRED")


def fetch_vix_polygon() -> float:
    """Fetch previous day VIX close from Polygon."""
    if not POLYGON_API_KEY:
        raise ValueError("POLYGON_API_KEY not set")
    url = f"https://api.polygon.io/v2/aggs/ticker/VIX/prev"
    params = {"adjusted": "true", "apiKey": POLYGON_API_KEY}
    log.info("Fetching VIX from Polygon (fallback)...")
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    if not results:
        raise ValueError("No results from Polygon VIX endpoint")
    return float(results[0]["c"])


def main():
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    vix_value = None
    source = None

    # Try FRED first
    try:
        vix_value = fetch_vix_fred()
        source = "fred"
        log.info(f"VIX from FRED: {vix_value}")
    except Exception as e:
        log.warning(f"FRED fetch failed: {e}")

    # Fallback to Polygon
    if vix_value is None:
        try:
            vix_value = fetch_vix_polygon()
            source = "polygon"
            log.info(f"VIX from Polygon: {vix_value}")
        except Exception as e:
            log.error(f"Polygon fetch failed: {e}")

    # Both failed
    if vix_value is None:
        result = {
            "error": "Both FRED and Polygon VIX sources failed",
            "trading_allowed": False,
            "timestamp": timestamp,
        }
        print(json.dumps(result))
        sys.exit(1)

    regime, size_multiplier, trading_allowed = classify_regime(vix_value)
    log.info(f"Regime: {regime}, size_multiplier: {size_multiplier}, trading_allowed: {trading_allowed}")

    result = {
        "vix": round(vix_value, 2),
        "regime": regime,
        "size_multiplier": size_multiplier,
        "trading_allowed": trading_allowed,
        "source": source,
        "timestamp": timestamp,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
