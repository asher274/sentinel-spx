#!/usr/bin/env python3
"""
uw_flow_scan.py — Unusual Whales options flow scanner for SPX/SPY.

Scans for large options prints on SPX and SPY over the last 2 hours,
classifies net flow direction, and flags significant institutional positioning.

Output JSON to stdout. Logging to stderr.
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

# Load env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.trading"))

# Logging to stderr
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [uw_flow_scan] %(levelname)s %(message)s",
)
log = logging.getLogger("uw_flow_scan")

UW_API_KEY = os.getenv("UNUSUAL_WHALES_API_KEY", "") or os.getenv("UW_API_KEY", "")
UW_BASE_URL = "https://api.unusualwhales.com/api"

# Minimum premium to qualify as a "large print" (USD)
LARGE_PRINT_THRESHOLD = 250_000

# Net delta thresholds for signal classification (USD premium)
BULLISH_DELTA_THRESHOLD = 5_000_000   # >$5M net call premium -> bullish
BEARISH_DELTA_THRESHOLD = -5_000_000  # <-$5M net call premium -> bearish

# Symbols to scan
SCAN_SYMBOLS = ["SPX", "SPY"]

# Lookback window in hours
LOOKBACK_HOURS = 2


def fetch_flow(symbol: str) -> list:
    """
    Fetch options flow for a given symbol from Unusual Whales.
    Returns list of flow records.
    """
    if not UW_API_KEY:
        raise ValueError("UNUSUAL_WHALES_API_KEY not set")

    url = f"{UW_BASE_URL}/stock/{symbol}/flow"
    headers = {
        "Authorization": f"Bearer {UW_API_KEY}",
        "Accept": "application/json",
    }
    params = {
        "limit": 200,
        "order": "desc",
    }

    log.info(f"Fetching UW flow for {symbol}...")
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    # UW API can return list or dict with 'data' key
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = data.get("data", data.get("flow", data.get("results", [])))
    else:
        records = []

    log.info(f"{symbol}: {len(records)} flow records returned")
    return records


def parse_flow_records(records: list, since_dt: datetime, symbol: str) -> tuple:
    """
    Filter records to lookback window and identify large prints.

    Returns:
        (large_prints, net_delta)
        - large_prints: list of large flow records
        - net_delta: net call premium minus put premium in USD
    """
    large_prints = []
    net_delta = 0.0
    total_processed = 0

    for record in records:
        # Parse timestamp — UW uses 'created_at', 'timestamp', or 'date'
        ts_raw = record.get("created_at") or record.get("timestamp") or record.get("date") or ""
        if ts_raw:
            try:
                if isinstance(ts_raw, (int, float)):
                    record_dt = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
                else:
                    ts_clean = str(ts_raw).replace("Z", "+00:00")
                    record_dt = datetime.fromisoformat(ts_clean)
                if record_dt < since_dt:
                    continue
            except (ValueError, TypeError) as e:
                log.debug(f"Could not parse timestamp '{ts_raw}': {e}")
                # Include record if timestamp is unparseable (assume recent)

        total_processed += 1

        # Parse premium
        premium_raw = record.get("premium") or record.get("total_premium") or 0
        try:
            premium = float(premium_raw)
        except (ValueError, TypeError):
            premium = 0.0

        # Parse contract type
        contract_type = (
            record.get("type") or record.get("contract_type")
            or record.get("put_call") or record.get("side") or ""
        ).lower()
        is_call = "call" in contract_type
        is_put = "put" in contract_type

        # Accumulate net delta
        if is_call:
            net_delta += premium
        elif is_put:
            net_delta -= premium

        # Classify as large print
        if premium >= LARGE_PRINT_THRESHOLD:
            sentiment = (
                record.get("sentiment")
                or record.get("bullish_bearish")
                or ("bullish" if is_call else "bearish" if is_put else "unknown")
            )
            large_prints.append({
                "symbol": symbol,
                "contract_type": "call" if is_call else "put" if is_put else "unknown",
                "premium": round(premium, 2),
                "strike": record.get("strike") or record.get("strike_price"),
                "expiry": (
                    record.get("expiry") or record.get("expiration_date")
                    or record.get("expires") or record.get("expiration")
                ),
                "sentiment": sentiment,
                "timestamp": ts_raw,
            })

    log.info(
        f"{symbol}: processed {total_processed} recent records, "
        f"{len(large_prints)} large prints, net_delta={net_delta:,.0f}"
    )
    return large_prints, net_delta


def classify_flow_signal(spx_net_delta: float) -> str:
    """Classify overall flow signal based on net SPX/SPY delta."""
    if spx_net_delta >= BULLISH_DELTA_THRESHOLD:
        return "bullish"
    elif spx_net_delta <= BEARISH_DELTA_THRESHOLD:
        return "bearish"
    else:
        return "neutral"


def main():
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    since_dt = datetime.now(tz=timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info(f"Scanning UW flow for last {LOOKBACK_HOURS}h (since {since_iso})")

    all_large_prints = []
    total_net_delta = 0.0
    errors = []

    for symbol in SCAN_SYMBOLS:
        try:
            records = fetch_flow(symbol)
            large_prints, net_delta = parse_flow_records(records, since_dt, symbol)
            all_large_prints.extend(large_prints)
            total_net_delta += net_delta
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "N/A"
            err = f"{symbol} HTTP {status_code}: {e}"
            log.error(err)
            errors.append(err)
        except Exception as e:
            err = f"{symbol} error: {e}"
            log.error(err, exc_info=True)
            errors.append(err)

    # Sort large prints by premium descending
    all_large_prints.sort(key=lambda x: x["premium"], reverse=True)

    flow_signal = classify_flow_signal(total_net_delta)
    log.info(
        f"Flow signal: {flow_signal} | net_delta={total_net_delta:,.0f} "
        f"| large_prints={len(all_large_prints)}"
    )

    result = {
        "flow_signal": flow_signal,
        "large_prints": all_large_prints[:20],  # cap output at 20 prints
        "spx_net_delta": round(total_net_delta, 2),
        "timestamp": timestamp,
    }

    if errors:
        result["errors"] = errors

    print(json.dumps(result))

    if errors and not all_large_prints:
        # All sources errored with no data
        sys.exit(1)


if __name__ == "__main__":
    main()
