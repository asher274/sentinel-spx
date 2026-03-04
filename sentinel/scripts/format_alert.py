#!/usr/bin/env python3
"""
format_alert.py — Format a generate_signal.py GO decision into a Discord-ready alert.

Reads generate_signal.py JSON output from stdin.
Produces a rich Discord-formatted alert with strikes, credit, stops,
VIX regime, GEX walls, and confidence score.

Usage:
    python generate_signal.py | python format_alert.py

Output JSON to stdout. Logging to stderr.
"""

import json
import logging
import sys
from datetime import datetime

# Logging to stderr
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [format_alert] %(levelname)s %(message)s",
)
log = logging.getLogger("format_alert")

# Confidence thresholds for display
CONFIDENCE_HIGH = 0.90
CONFIDENCE_MED = 0.75

# Emoji constants
EMOJI_GO = "\U0001f7e2"        # green circle
EMOJI_WARN = "\U0001f7e1"      # yellow circle
EMOJI_STOP = "\U0001f534"      # red circle
EMOJI_CHART = "\U0001f4c8"     # chart increasing
EMOJI_SHIELD = "\U0001f6e1"    # shield
EMOJI_TARGET = "\U0001f3af"    # target
EMOJI_CLOCK = "\u23f0"         # alarm clock
EMOJI_FIRE = "\U0001f525"      # fire
EMOJI_SNOWFLAKE = "\u2744"     # snowflake


def confidence_label(confidence: float) -> str:
    """Return a confidence label string."""
    if confidence >= CONFIDENCE_HIGH:
        return f"{EMOJI_GO} HIGH ({confidence:.0%})"
    elif confidence >= CONFIDENCE_MED:
        return f"{EMOJI_WARN} MEDIUM ({confidence:.0%})"
    else:
        return f"{EMOJI_STOP} LOW ({confidence:.0%})"


def vix_regime_emoji(regime: str) -> str:
    """Return an emoji for the VIX regime."""
    mapping = {
        "low": EMOJI_SNOWFLAKE,
        "normal": EMOJI_CHART,
        "elevated": EMOJI_FIRE,
        "extreme": EMOJI_STOP,
    }
    return mapping.get(regime, EMOJI_CHART)


def format_filter_status(filters: dict) -> str:
    """Render filter pass/fail summary as a compact block."""
    lines = []
    status_map = {"pass": "\u2705", "fail": "\u274c", "warn": "\u26a0\ufe0f", "pending": "\u23f3"}

    for key, val in filters.items():
        if isinstance(val, dict):
            status = val.get("status", "pending")
            emoji = status_map.get(status, "\u2753")
            detail = ""
            if key == "vix":
                vix = val.get("value")
                regime = val.get("regime", "")
                if vix is not None:
                    detail = f" VIX {vix} ({regime})"
            elif key == "gex":
                call_wall = val.get("call_wall")
                put_wall = val.get("put_wall")
                if call_wall is not None and put_wall is not None:
                    detail = f" walls {put_wall}/{call_wall}"
            elif key == "calendar":
                events = val.get("events_today", [])
                if events:
                    names = [e.get("name", "") for e in events if isinstance(e, dict)]
                    detail = f" ({', '.join(names)})"
            elif key == "polymarket":
                risk = val.get("risk_signal", "")
                if risk:
                    detail = f" macro={risk}"
            lines.append(f"  {emoji} `{key.upper()}`{detail}")
        else:
            status = str(val)
            emoji = status_map.get(status, "\u2753")
            lines.append(f"  {emoji} `{key.upper()}`")

    return "\n".join(lines)


def build_alert_text(signal: dict) -> tuple:
    """
    Build Discord alert text and a short summary line from a GO signal.

    Returns:
        (alert_text, summary_line)
    """
    setup = signal.get("setup", {}) or {}
    filters = signal.get("filters", {}) or {}
    confidence = signal.get("confidence", 1.0)
    decision = signal.get("decision", "GO")
    reason = signal.get("reason", "")
    ts = signal.get("timestamp", "")

    short_call = setup.get("short_call")
    long_call = setup.get("long_call")
    short_put = setup.get("short_put")
    long_put = setup.get("long_put")
    credit_low = setup.get("credit_target_low")
    credit_high = setup.get("credit_target_high")
    stop_per_side = setup.get("stop_per_side")
    profit_target_pct = setup.get("profit_target_pct", 50)
    wing_width = setup.get("wing_width")

    # VIX info from filters
    vix_info = filters.get("vix", {}) if isinstance(filters.get("vix"), dict) else {}
    vix_value = vix_info.get("value", "N/A")
    vix_regime = vix_info.get("regime", "N/A")
    vix_emoji = vix_regime_emoji(vix_regime)

    # GEX walls from filters
    gex_info = filters.get("gex", {}) if isinstance(filters.get("gex"), dict) else {}
    call_wall = gex_info.get("call_wall", "N/A")
    put_wall = gex_info.get("put_wall", "N/A")

    conf_label = confidence_label(confidence)

    if decision == "GO" and setup:
        # --- Full trade alert ---
        credit_range = (
            f"${credit_low:.2f}–${credit_high:.2f}"
            if credit_low is not None and credit_high is not None
            else "N/A"
        )
        stop_display = f"${stop_per_side:.2f}/side" if stop_per_side is not None else "N/A"
        profit_display = (
            f"50% close (~${credit_low * 0.5:.2f})"
            if credit_low is not None else f"{profit_target_pct}%"
        )
        wing_display = f"{wing_width}pt" if wing_width is not None else "N/A"

        alert_text = (
            f"{EMOJI_GO} **SENTINEL — IRON CONDOR SIGNAL** {EMOJI_GO}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"**SETUP: SPX 0DTE Iron Condor**\n"
            f"```\n"
            f"CALL SPREAD:  {short_call} / {long_call}\n"
            f"PUT SPREAD:   {long_put} / {short_put}\n"
            f"WING WIDTH:   {wing_display}\n"
            f"```\n"
            f"\n"
            f"{EMOJI_TARGET} **Credit Target:** {credit_range}\n"
            f"{EMOJI_SHIELD} **Stop (per side):** {stop_display}\n"
            f"{EMOJI_TARGET} **Profit Target:** {profit_display}\n"
            f"{EMOJI_CLOCK} **Force Close:** 3:45 PM ET\n"
            f"\n"
            f"**CONDITIONS**\n"
            f"{vix_emoji} VIX: `{vix_value}` — regime `{vix_regime}`\n"
            f"{EMOJI_CHART} GEX Walls: put `{put_wall}` / call `{call_wall}`\n"
            f"\n"
            f"**FILTER RESULTS**\n"
            f"{format_filter_status(filters)}\n"
            f"\n"
            f"**CONFIDENCE:** {conf_label}\n"
            f"\n"
            f"_{reason}_\n"
            f"_Signal time: {ts} UTC_"
        )

        summary_line = (
            f"{EMOJI_GO} SPX IC {short_put}/{long_put} | {short_call}/{long_call} "
            f"| credit {credit_range} | stop {stop_display} | conf {confidence:.0%}"
        )

    else:
        # --- NO_TRADE alert ---
        alert_text = (
            f"{EMOJI_STOP} **SENTINEL — NO TRADE**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"**Decision:** {decision}\n"
            f"**Reason:** {reason}\n"
            f"\n"
            f"**FILTER RESULTS**\n"
            f"{format_filter_status(filters)}\n"
            f"\n"
            f"**CONFIDENCE:** {conf_label}\n"
            f"\n"
            f"_Signal time: {ts} UTC_"
        )

        summary_line = f"{EMOJI_STOP} NO TRADE — {reason} (conf {confidence:.0%})"

    return alert_text, summary_line


def main():
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    # Read generate_signal.py JSON from stdin
    log.info("Reading signal JSON from stdin...")
    try:
        raw_input = sys.stdin.read().strip()
        if not raw_input:
            log.error("No input received on stdin")
            result = {
                "alert_text": "ERROR: No signal input received",
                "summary_line": "ERROR: No signal",
                "error": "Empty stdin",
                "timestamp": timestamp,
            }
            print(json.dumps(result))
            sys.exit(1)

        signal = json.loads(raw_input)
        log.info(f"Parsed signal: decision={signal.get('decision')}, confidence={signal.get('confidence')}")

    except json.JSONDecodeError as e:
        log.error(f"Failed to parse signal JSON from stdin: {e}")
        result = {
            "alert_text": "ERROR: Invalid signal JSON",
            "summary_line": "ERROR: Invalid signal",
            "error": f"JSON parse error: {e}",
            "timestamp": timestamp,
        }
        print(json.dumps(result))
        sys.exit(1)

    try:
        alert_text, summary_line = build_alert_text(signal)
        log.info("Alert formatted successfully")

        result = {
            "alert_text": alert_text,
            "summary_line": summary_line,
            "timestamp": timestamp,
        }
        print(json.dumps(result))

    except Exception as e:
        log.error(f"Alert formatting failed: {e}", exc_info=True)
        result = {
            "alert_text": f"ERROR: {e}",
            "summary_line": "ERROR: Formatting failed",
            "error": str(e),
            "timestamp": timestamp,
        }
        print(json.dumps(result))
        sys.exit(1)


if __name__ == "__main__":
    main()
