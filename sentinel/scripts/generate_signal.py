#!/usr/bin/env python3
"""
generate_signal.py — Master signal synthesizer for Sentinel bot.

Runs all filter scripts in sequence, aggregates results, and outputs
a GO/NO_TRADE decision with full iron condor setup parameters.

Output JSON to stdout. Logging to stderr.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime

import pytz
from dotenv import load_dotenv

# Load env
dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env.trading")
load_dotenv(dotenv_path=dotenv_path)

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [generate_signal] %(levelname)s %(message)s",
)
log = logging.getLogger("generate_signal")

ET = pytz.timezone("America/New_York")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Entry window: 10:05 AM – 10:35 AM ET
ENTRY_WINDOW_START = (10, 5)
ENTRY_WINDOW_END = (10, 35)

# Non-trading days (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun)
BLOCKED_WEEKDAYS = {2, 4}  # Wednesday=2, Friday=4
BLOCKED_WEEKDAY_NAMES = {2: "Wednesday", 4: "Friday"}

# Wing width params
BASE_WING_WIDTH = 25
ELEVATED_VIX_EXTRA = 5

# Credit targets
CREDIT_TARGET_LOW = 1.50
CREDIT_TARGET_HIGH = 2.50
PROFIT_TARGET_PCT = 50


def run_script(script_name: str) -> dict:
    """
    Run a script as a subprocess, capture JSON output from stdout.
    Returns parsed dict or error dict.
    """
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    log.info(f"Running {script_name}...")

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "PYTHONPATH": SCRIPTS_DIR},
        )

        # Log stderr from subprocesses
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                log.debug(f"[{script_name}] {line}")

        if result.stdout.strip():
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse JSON from {script_name}: {e}")
                log.error(f"Raw stdout: {result.stdout[:500]}")
                return {"error": f"JSON parse error from {script_name}: {e}"}

        if result.returncode != 0:
            return {"error": f"{script_name} exited with code {result.returncode}"}

        return {"error": f"{script_name} produced no output"}

    except subprocess.TimeoutExpired:
        log.error(f"{script_name} timed out")
        return {"error": f"{script_name} timed out after 60s"}
    except Exception as e:
        log.error(f"Failed to run {script_name}: {e}", exc_info=True)
        return {"error": str(e)}


def no_trade(reason: str, filters: dict, confidence: float, timestamp: str) -> dict:
    """Build a NO_TRADE result dict."""
    return {
        "decision": "NO_TRADE",
        "reason": reason,
        "confidence": round(confidence, 2),
        "setup": None,
        "filters": filters,
        "timestamp": timestamp,
    }


def main():
    now_et = datetime.now(ET)
    timestamp = now_et.strftime("%Y-%m-%dT%H:%M:%S")
    confidence = 1.0

    filters = {
        "day_of_week": "pending",
        "time_window": "pending",
        "vix": {"status": "pending"},
        "calendar": {"status": "pending"},
        "gex": {"status": "pending"},
        "polymarket": {"status": "pending"},
    }

    # --- Filter 1: Day of week ---
    weekday = now_et.weekday()
    if weekday in BLOCKED_WEEKDAYS:
        day_name = BLOCKED_WEEKDAY_NAMES[weekday]
        filters["day_of_week"] = "fail"
        log.info(f"Day of week filter: FAIL ({day_name})")
        result = no_trade(f"Non-trading day ({day_name} filtered)", filters, confidence, timestamp)
        print(json.dumps(result))
        return

    filters["day_of_week"] = "pass"
    log.info(f"Day of week filter: PASS ({now_et.strftime('%A')})")

    # --- Filter 2: Time window ---
    current_hour = now_et.hour
    current_minute = now_et.minute
    current_time = (current_hour, current_minute)

    in_window = ENTRY_WINDOW_START <= current_time <= ENTRY_WINDOW_END
    if not in_window:
        filters["time_window"] = "fail"
        log.info(f"Time window filter: FAIL ({now_et.strftime('%H:%M')} ET, window is 10:05–10:35)")
        result = no_trade("Outside entry window", filters, confidence, timestamp)
        print(json.dumps(result))
        return

    filters["time_window"] = "pass"
    log.info(f"Time window filter: PASS ({now_et.strftime('%H:%M')} ET)")

    # --- Filter 3: VIX ---
    vix_data = run_script("check_vix.py")

    if vix_data.get("error"):
        filters["vix"] = {"status": "fail", "error": vix_data["error"]}
        log.error(f"VIX filter: FAIL (error: {vix_data['error']})")
        result = no_trade(f"VIX check failed: {vix_data['error']}", filters, confidence, timestamp)
        print(json.dumps(result))
        return

    vix_value = vix_data.get("vix")
    vix_regime = vix_data.get("regime", "unknown")
    trading_allowed = vix_data.get("trading_allowed", False)

    filters["vix"] = {
        "status": "pass" if trading_allowed else "fail",
        "value": vix_value,
        "regime": vix_regime,
    }

    if not trading_allowed:
        log.info(f"VIX filter: FAIL (regime={vix_regime}, vix={vix_value})")
        result = no_trade(f"VIX too high: {vix_value} ({vix_regime})", filters, confidence, timestamp)
        print(json.dumps(result))
        return

    log.info(f"VIX filter: PASS (vix={vix_value}, regime={vix_regime})")

    # --- Filter 4: Calendar ---
    cal_data = run_script("check_calendar.py")

    if cal_data.get("error") and "events_today" not in cal_data:
        filters["calendar"] = {"status": "fail", "error": cal_data["error"]}
        log.error(f"Calendar filter: FAIL (error: {cal_data['error']})")
        result = no_trade(f"Calendar check failed: {cal_data['error']}", filters, confidence, timestamp)
        print(json.dumps(result))
        return

    safe_to_trade = cal_data.get("safe_to_trade", True)
    events_today = cal_data.get("events_today", [])

    filters["calendar"] = {
        "status": "pass" if safe_to_trade else "fail",
        "events_today": events_today,
        "blocking_event_active": cal_data.get("blocking_event_active", False),
        "blocking_in_30min": cal_data.get("blocking_in_30min", False),
    }

    if not safe_to_trade:
        event_names = [e["name"] for e in events_today]
        log.info(f"Calendar filter: FAIL (events: {event_names})")
        result = no_trade(f"High-impact event blocking trade: {', '.join(event_names)}", filters, confidence, timestamp)
        print(json.dumps(result))
        return

    log.info(f"Calendar filter: PASS (events today: {[e['name'] for e in events_today] or 'none'})")

    # --- Filter 5: GEX ---
    gex_data = run_script("check_gex.py")

    if gex_data.get("error") and "gex_regime" not in gex_data:
        filters["gex"] = {"status": "fail", "error": gex_data["error"]}
        log.error(f"GEX filter: FAIL (error: {gex_data['error']})")
        result = no_trade(f"GEX check failed: {gex_data['error']}", filters, confidence, timestamp)
        print(json.dumps(result))
        return

    gex_regime = gex_data.get("gex_regime", "unknown")
    call_wall = gex_data.get("call_wall")
    put_wall = gex_data.get("put_wall")

    filters["gex"] = {
        "status": "pass" if gex_regime == "positive" else "fail",
        "regime": gex_regime,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "net_gex": gex_data.get("net_gex"),
        "zero_gamma": gex_data.get("zero_gamma"),
    }

    if gex_regime != "positive":
        log.info(f"GEX filter: FAIL (regime={gex_regime})")
        result = no_trade(f"Negative GEX regime — dealer hedging creates adverse conditions", filters, confidence, timestamp)
        print(json.dumps(result))
        return

    log.info(f"GEX filter: PASS (regime={gex_regime}, call_wall={call_wall}, put_wall={put_wall})")

    # --- Filter 6: Polymarket ---
    poly_data = run_script("polymarket_scan.py")

    macro_risk_signal = poly_data.get("macro_risk_signal", "unknown")

    if macro_risk_signal == "unknown" and poly_data.get("error"):
        # API unavailable — log but don't block (treat as low risk)
        log.warning(f"Polymarket unavailable: {poly_data['error']} — treating as 'low'")
        macro_risk_signal = "low"

    filters["polymarket"] = {
        "status": "pass" if macro_risk_signal in ("low", "unknown") else ("warn" if macro_risk_signal == "medium" else "fail"),
        "risk_signal": macro_risk_signal,
        "relevant_count": poly_data.get("relevant_count", 0),
    }

    if macro_risk_signal == "high":
        log.info(f"Polymarket filter: FAIL (macro_risk_signal=high)")
        result = no_trade("High macro risk signal from Polymarket", filters, confidence, timestamp)
        print(json.dumps(result))
        return

    if macro_risk_signal == "medium":
        log.warning("Polymarket shows MEDIUM macro risk — proceeding with reduced confidence")
        confidence -= 0.1

    log.info(f"Polymarket filter: PASS (risk_signal={macro_risk_signal})")

    # --- All filters passed — build setup ---
    log.info("All filters passed. Building iron condor setup...")

    # Validate walls exist
    if call_wall is None or put_wall is None:
        log.error("Cannot build setup: call_wall or put_wall is None")
        result = no_trade("GEX walls undefined — cannot build setup", filters, confidence, timestamp)
        print(json.dumps(result))
        return

    # Wing width
    wing_width = BASE_WING_WIDTH
    if vix_regime == "elevated":
        wing_width += ELEVATED_VIX_EXTRA
        log.info(f"VIX elevated — wing width expanded to {wing_width}pt")

    # Strike calculations
    short_call = call_wall + 10
    short_put = put_wall - 10
    long_call = short_call + wing_width
    long_put = short_put - wing_width

    stop_per_side = CREDIT_TARGET_LOW

    setup = {
        "short_call": short_call,
        "long_call": long_call,
        "short_put": short_put,
        "long_put": long_put,
        "credit_target_low": CREDIT_TARGET_LOW,
        "credit_target_high": CREDIT_TARGET_HIGH,
        "stop_per_side": stop_per_side,
        "profit_target_pct": PROFIT_TARGET_PCT,
        "wing_width": wing_width,
    }

    log.info(
        f"Setup: IC {short_put}/{long_put} | {short_call}/{long_call} "
        f"wing={wing_width}pt credit={CREDIT_TARGET_LOW}–{CREDIT_TARGET_HIGH} "
        f"stop={stop_per_side} target={PROFIT_TARGET_PCT}%"
    )

    result = {
        "decision": "GO",
        "reason": "All filters passed",
        "confidence": round(confidence, 2),
        "setup": setup,
        "filters": filters,
        "timestamp": timestamp,
    }

    print(json.dumps(result, indent=2))
    log.info(f"Signal: GO | confidence={confidence:.2f}")


if __name__ == "__main__":
    main()
