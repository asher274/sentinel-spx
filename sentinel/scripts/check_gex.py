#!/usr/bin/env python3
"""
check_gex.py — Calculate Gamma Exposure (GEX) for SPX 0DTE options.

Fetches SPX options chain from Polygon snapshot API for today's expiration.
Calculates per-strike GEX, identifies call wall, put wall, zero-gamma strike.

Output JSON to stdout. Logging to stderr.
"""

import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.trading"))

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [check_gex] %(levelname)s %(message)s",
)
log = logging.getLogger("check_gex")

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
BASE_URL = "https://api.polygon.io/v3/snapshot/options/SPX"


def fetch_options_chain(expiration_date: str) -> list[dict]:
    """Fetch full SPX options chain for given expiration date, handling pagination."""
    if not POLYGON_API_KEY:
        raise ValueError("POLYGON_API_KEY not set")

    all_results = []
    params = {
        "expiration_date": expiration_date,
        "limit": 250,
        "apiKey": POLYGON_API_KEY,
    }
    url = BASE_URL

    page = 0
    while url:
        page += 1
        log.info(f"Fetching options chain page {page} from Polygon...")
        resp = requests.get(url, params=params if page == 1 else {}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        all_results.extend(results)
        log.info(f"Page {page}: got {len(results)} contracts (total so far: {len(all_results)})")

        # Handle pagination via next_url
        next_url = data.get("next_url")
        if next_url:
            url = f"{next_url}&apiKey={POLYGON_API_KEY}"
            params = {}
        else:
            break

    return all_results


def get_spot_price(contracts: list[dict]) -> float:
    """Extract underlying spot price from any contract's underlying_asset."""
    for c in contracts:
        details = c.get("underlying_asset", {})
        price = details.get("price")
        if price:
            return float(price)
        # Also try inside 'day' field at top level
        day = c.get("day", {})
        if day.get("underlying_price"):
            return float(day["underlying_price"])
    raise ValueError("Could not determine SPX spot price from options chain")


def calculate_gex(contracts: list[dict], spot: float) -> dict:
    """
    Calculate GEX per strike and aggregate metrics.

    Returns dict with: net_gex, call_wall, put_wall, zero_gamma, gex_regime,
                       strikes_analyzed, per_strike data.
    """
    # Aggregate by strike
    call_gex_by_strike = defaultdict(float)
    put_gex_by_strike = defaultdict(float)
    skipped = 0

    for c in contracts:
        details = c.get("details", {})
        greeks = c.get("greeks", {})
        oi = c.get("open_interest", 0) or 0

        gamma = greeks.get("gamma")
        if gamma is None:
            skipped += 1
            continue

        gamma = float(gamma)
        oi = float(oi)
        strike = details.get("strike_price")
        contract_type = details.get("contract_type", "").lower()

        if strike is None:
            skipped += 1
            continue

        strike = float(strike)

        gex_contribution = oi * gamma * 100 * spot

        if contract_type == "call":
            call_gex_by_strike[strike] += gex_contribution
        elif contract_type == "put":
            put_gex_by_strike[strike] += gex_contribution * -1

    if skipped > 0:
        log.warning(f"Skipped {skipped} contracts missing gamma or strike data")

    all_strikes = sorted(set(call_gex_by_strike.keys()) | set(put_gex_by_strike.keys()))

    if not all_strikes:
        raise ValueError("No valid strikes with gamma data found")

    log.info(f"Strikes analyzed: {len(all_strikes)}")

    # Per-strike net GEX
    net_gex_by_strike = {}
    for strike in all_strikes:
        net_gex_by_strike[strike] = call_gex_by_strike[strike] + put_gex_by_strike[strike]

    # Total net GEX
    total_net_gex = sum(net_gex_by_strike.values())

    # Call wall: strike with highest cumulative positive call GEX
    call_wall = max(call_gex_by_strike, key=lambda s: call_gex_by_strike[s]) if call_gex_by_strike else None

    # Put wall: strike with highest cumulative negative put GEX (most negative)
    put_wall = min(put_gex_by_strike, key=lambda s: put_gex_by_strike[s]) if put_gex_by_strike else None

    # Zero gamma: strike where cumulative net GEX crosses zero (closest to zero crossing)
    cumulative = 0.0
    zero_gamma = None
    prev_strike = None
    prev_cumulative = 0.0

    for strike in all_strikes:
        cumulative += net_gex_by_strike[strike]
        if prev_strike is not None and prev_cumulative * cumulative < 0:
            # Sign change — pick the strike closer to zero
            if abs(cumulative) < abs(prev_cumulative):
                zero_gamma = strike
            else:
                zero_gamma = prev_strike
        prev_strike = strike
        prev_cumulative = cumulative

    # If no crossing found, use strike nearest to zero cumulative
    if zero_gamma is None:
        zero_gamma = min(all_strikes, key=lambda s: abs(
            sum(net_gex_by_strike[k] for k in all_strikes if k <= s)
        ))

    gex_regime = "positive" if total_net_gex > 0 else "negative"

    return {
        "gex_regime": gex_regime,
        "net_gex": round(total_net_gex, 0),
        "call_wall": call_wall,
        "put_wall": put_wall,
        "zero_gamma": zero_gamma,
        "strikes_analyzed": len(all_strikes),
    }


def main():
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    today_str = date.today().strftime("%Y-%m-%d")

    try:
        contracts = fetch_options_chain(today_str)
        log.info(f"Total contracts fetched: {len(contracts)}")

        if not contracts:
            result = {
                "error": f"No contracts returned for expiration {today_str}",
                "gex_regime": "unknown",
                "timestamp": timestamp,
            }
            print(json.dumps(result))
            sys.exit(1)

        spot = get_spot_price(contracts)
        log.info(f"SPX spot price: {spot}")

        gex_data = calculate_gex(contracts, spot)

        result = {
            "gex_regime": gex_data["gex_regime"],
            "net_gex": int(gex_data["net_gex"]),
            "call_wall": gex_data["call_wall"],
            "put_wall": gex_data["put_wall"],
            "zero_gamma": gex_data["zero_gamma"],
            "spot": round(spot, 2),
            "strikes_analyzed": gex_data["strikes_analyzed"],
            "timestamp": timestamp,
        }
        print(json.dumps(result))

    except Exception as e:
        log.error(f"GEX calculation failed: {e}", exc_info=True)
        result = {
            "error": str(e),
            "gex_regime": "unknown",
            "timestamp": timestamp,
        }
        print(json.dumps(result))
        sys.exit(1)


if __name__ == "__main__":
    main()
