#!/usr/bin/env python3
"""
daily_report.py — End-of-day report generator for Sentinel Phase 0.

Reads paper_trades.json for today's trades and computes daily P&L,
win rate, signal qualification stats, and formats a full report.

Usage:
    python daily_report.py
    python daily_report.py --date 2026-03-04

Output JSON to stdout. Logging to stderr.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, date

import pytz
from dotenv import load_dotenv

# Load env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.trading"))

# Logging to stderr
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [daily_report] %(levelname)s %(message)s",
)
log = logging.getLogger("daily_report")

ET = pytz.timezone("America/New_York")

TRADES_FILE = os.path.join(os.path.dirname(__file__), "..", "paper_trades.json")
MEMORY_FILE = os.path.join(os.path.dirname(__file__), "..", "openclaw", "MEMORY.md")

# Trading day classification
TRADING_DAYS = {0: "Monday", 1: "Tuesday", 3: "Thursday"}
NON_TRADING_DAYS = {2: "Wednesday", 4: "Friday", 5: "Saturday", 6: "Sunday"}


def load_trades() -> dict:
    """Load all trades from paper_trades.json."""
    if not os.path.exists(TRADES_FILE):
        log.warning(f"No trades file at {TRADES_FILE}")
        return {}
    with open(TRADES_FILE, "r") as f:
        return json.load(f)


def load_memory_notes(report_date: date) -> str:
    """
    Read MEMORY.md and extract any notes relevant to the report date.
    Returns a plain string summary or empty string if unavailable.
    """
    if not os.path.exists(MEMORY_FILE):
        log.debug("MEMORY.md not found — skipping memory notes")
        return ""
    try:
        with open(MEMORY_FILE, "r") as f:
            content = f.read()
        # Return first 2000 chars of memory as context
        return content[:2000].strip()
    except Exception as e:
        log.warning(f"Could not read MEMORY.md: {e}")
        return ""


def filter_trades_for_date(trades: dict, report_date: date) -> tuple:
    """
    Split all trades into those entered today (entered_today)
    and those closed today (closed_today).

    Returns: (entered_today, closed_today)
    Both are dicts of {trade_id: trade_record}.
    """
    date_str = report_date.strftime("%Y-%m-%d")
    entered_today = {}
    closed_today = {}

    for tid, trade in trades.items():
        entry_time = trade.get("entry_time", "")
        exit_time = trade.get("exit_time", "")

        if entry_time.startswith(date_str):
            entered_today[tid] = trade
        if exit_time and exit_time.startswith(date_str):
            closed_today[tid] = trade

    return entered_today, closed_today


def classify_day_type(report_date: date) -> str:
    """Return day type string: 'trading_day', 'non_trading_day', or 'weekend'."""
    wd = report_date.weekday()
    if wd in TRADING_DAYS:
        return f"trading_day ({TRADING_DAYS[wd]})"
    elif wd in NON_TRADING_DAYS:
        if wd >= 5:
            return "weekend"
        return f"non_trading_day ({NON_TRADING_DAYS[wd]})"
    return "unknown"


def compute_stats(closed_today: dict) -> dict:
    """
    Compute P&L stats for trades closed today.

    Returns dict with: daily_pnl, win_count, loss_count, win_rate, trade_details
    """
    daily_pnl = 0.0
    win_count = 0
    loss_count = 0
    trade_details = []

    for tid, trade in closed_today.items():
        pnl = trade.get("pnl")
        if pnl is None:
            log.warning(f"Trade {tid} has no P&L recorded — skipping from stats")
            continue

        pnl = float(pnl)
        daily_pnl += pnl

        if pnl > 0:
            win_count += 1
        else:
            loss_count += 1

        trade_details.append({
            "trade_id": tid,
            "entry_time": trade.get("entry_time"),
            "exit_time": trade.get("exit_time"),
            "short_call": trade.get("short_call"),
            "long_call": trade.get("long_call"),
            "short_put": trade.get("short_put"),
            "long_put": trade.get("long_put"),
            "credit_received": trade.get("credit_received"),
            "exit_credit": trade.get("exit_credit"),
            "pnl": round(pnl, 2),
            "exit_reason": trade.get("exit_reason"),
        })

    total_closed = win_count + loss_count
    win_rate = (win_count / total_closed) if total_closed > 0 else 0.0

    return {
        "daily_pnl": round(daily_pnl, 2),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 4),
        "trade_details": trade_details,
    }


def compute_cumulative_stats(all_trades: dict) -> dict:
    """Compute cumulative win rate and P&L across all closed trades."""
    total_pnl = 0.0
    total_wins = 0
    total_losses = 0

    for trade in all_trades.values():
        if trade.get("status") != "closed":
            continue
        pnl = trade.get("pnl")
        if pnl is None:
            continue
        pnl = float(pnl)
        total_pnl += pnl
        if pnl > 0:
            total_wins += 1
        else:
            total_losses += 1

    total_closed = total_wins + total_losses
    cumulative_win_rate = (total_wins / total_closed) if total_closed > 0 else 0.0

    return {
        "total_trades": len(all_trades),
        "total_closed": total_closed,
        "total_open": len([t for t in all_trades.values() if t.get("status") == "open"]),
        "cumulative_pnl": round(total_pnl, 2),
        "cumulative_wins": total_wins,
        "cumulative_losses": total_losses,
        "cumulative_win_rate": round(cumulative_win_rate, 4),
    }


def build_report_text(
    report_date: date,
    day_type: str,
    entered_today: dict,
    closed_today: dict,
    stats: dict,
    cumulative: dict,
    memory_notes: str,
) -> str:
    """Build human-readable report text for Discord posting."""

    date_str = report_date.strftime("%A, %B %d, %Y")
    pnl = stats["daily_pnl"]
    pnl_emoji = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
    win_rate_pct = stats["win_rate"] * 100
    cum_win_rate_pct = cumulative["cumulative_win_rate"] * 100

    lines = [
        f"\U0001f4ca **SENTINEL DAILY REPORT**",
        f"\U0001f4c5 {date_str}",
        f"\u2500" * 28,
        "",
        f"**Day Type:** {day_type}",
        "",
        f"**TODAY'S ACTIVITY**",
        f"\u2022 Signals generated: {len(entered_today)}",
        f"\u2022 Trades entered: {len(entered_today)}",
        f"\u2022 Trades closed: {len(closed_today)}",
        f"\u2022 Trades still open: {len([t for t in entered_today.values() if t.get('status') == 'open'])}",
        "",
        f"**TODAY'S P&L**",
        f"{pnl_emoji} Daily P&L: ${pnl:+.2f}",
        f"\u2022 Wins: {stats['win_count']} | Losses: {stats['loss_count']}",
        f"\u2022 Win rate today: {win_rate_pct:.1f}%",
        "",
        f"**CUMULATIVE (Phase 0)**",
        f"\u2022 Total trades: {cumulative['total_closed']} closed / {cumulative['total_open']} open",
        f"\u2022 Cumulative P&L: ${cumulative['cumulative_pnl']:+.2f}",
        f"\u2022 Win rate all-time: {cum_win_rate_pct:.1f}% ({cumulative['cumulative_wins']}W / {cumulative['cumulative_losses']}L)",
        "",
    ]

    # Trade details
    if stats["trade_details"]:
        lines.append(f"**TRADE DETAILS**")
        for td in stats["trade_details"]:
            pnl_sign = "+" if td["pnl"] >= 0 else ""
            lines.append(
                f"\u2022 [{td['trade_id']}] IC {td.get('short_put')}/{td.get('long_put')} | "
                f"{td.get('short_call')}/{td.get('long_call')} "
                f"| credit ${td.get('credit_received', 'N/A')} "
                f"| exit ${td.get('exit_credit', 'N/A')} "
                f"| P&L ${pnl_sign}{td['pnl']:.2f} "
                f"| {td.get('exit_reason', 'N/A')}"
            )
        lines.append("")

    # Phase 0 progress check
    target_trades = 50
    target_days = 30
    target_win_rate_low = 55.0
    target_win_rate_high = 65.0
    total_closed = cumulative["total_closed"]
    progress_trades = min(100, int(total_closed / target_trades * 100))
    win_rate_ok = target_win_rate_low <= cum_win_rate_pct <= target_win_rate_high or cum_win_rate_pct > target_win_rate_high

    lines.append(f"**PHASE 0 PROGRESS**")
    lines.append(f"\u2022 Trade count: {total_closed}/{target_trades} ({progress_trades}%)")
    lines.append(f"\u2022 Win rate: {cum_win_rate_pct:.1f}% (target: {target_win_rate_low}–{target_win_rate_high}%) {'✅' if win_rate_ok else '⚠️'}")
    lines.append("")

    if memory_notes:
        lines.append(f"**SYSTEM NOTES**")
        # Truncate memory notes for Discord
        note_preview = memory_notes[:500].replace("\n", " ").strip()
        lines.append(f"_{note_preview}_")
        lines.append("")

    lines.append(f"_Report generated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')} UTC_")

    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(description="Sentinel daily report generator")
    parser.add_argument(
        "--date", default=None,
        help="Report date (YYYY-MM-DD). Defaults to today ET."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    now_et = datetime.now(ET)

    if args.date:
        try:
            report_date = date.fromisoformat(args.date)
        except ValueError:
            log.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        report_date = now_et.date()

    log.info(f"Generating daily report for {report_date}")

    try:
        all_trades = load_trades()
    except Exception as e:
        log.error(f"Failed to load trades: {e}")
        sys.exit(1)

    entered_today, closed_today = filter_trades_for_date(all_trades, report_date)
    day_type = classify_day_type(report_date)
    stats = compute_stats(closed_today)
    cumulative = compute_cumulative_stats(all_trades)
    memory_notes = load_memory_notes(report_date)

    # Qualification logic: a signal qualifies if all filters passed (decision == GO)
    # In paper_trade context we count all entered trades as qualified
    signals_generated = len(entered_today)
    qualifications = signals_generated
    no_qualifications = 0  # Would need signal log to compute accurately

    report_text = build_report_text(
        report_date=report_date,
        day_type=day_type,
        entered_today=entered_today,
        closed_today=closed_today,
        stats=stats,
        cumulative=cumulative,
        memory_notes=memory_notes,
    )

    result = {
        "date": report_date.strftime("%Y-%m-%d"),
        "day_type": day_type,
        "signals_generated": signals_generated,
        "qualifications": qualifications,
        "no_qualifications": no_qualifications,
        "trades_entered": len(entered_today),
        "trades_exited": len(closed_today),
        "daily_pnl": stats["daily_pnl"],
        "win_rate": stats["win_rate"],
        "cumulative_win_rate": cumulative["cumulative_win_rate"],
        "cumulative_pnl": cumulative["cumulative_pnl"],
        "total_trades_all_time": cumulative["total_closed"],
        "notes": memory_notes[:200] if memory_notes else None,
        "report_text": report_text,
        "timestamp": timestamp,
    }

    print(json.dumps(result, indent=2, default=str))
    log.info(f"Report complete: pnl={stats['daily_pnl']}, win_rate={stats['win_rate']:.1%}")


if __name__ == "__main__":
    main()
