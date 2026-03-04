#!/usr/bin/env python3
"""
paper_trade.py — Paper trade logger for Sentinel Phase 0.

Records simulated iron condor entries and exits to paper_trades.json.
Each trade has a unique ID. Exit updates the existing trade record.

Usage:
    # Log a new entry (reads setup JSON from stdin, or use --setup flag)
    python paper_trade.py --entry --setup '{"short_call": 5100, ...}'

    # Log an exit
    python paper_trade.py --exit --id TRADE_ID --credit-received 1.85 --exit-credit 0.92

    # List all open trades
    python paper_trade.py --list

Output JSON to stdout. Logging to stderr.
"""

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime

import pytz
from dotenv import load_dotenv

# Load env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.trading"))

# Logging to stderr
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [paper_trade] %(levelname)s %(message)s",
)
log = logging.getLogger("paper_trade")

ET = pytz.timezone("America/New_York")

# paper_trades.json lives one directory above scripts/ (project root)
TRADES_FILE = os.path.join(os.path.dirname(__file__), "..", "paper_trades.json")


def load_trades() -> dict:
    """Load trade log from paper_trades.json. Returns dict keyed by trade_id."""
    if not os.path.exists(TRADES_FILE):
        log.info(f"No existing trades file at {TRADES_FILE}. Starting fresh.")
        return {}
    try:
        with open(TRADES_FILE, "r") as f:
            data = json.load(f)
        log.info(f"Loaded {len(data)} trades from {TRADES_FILE}")
        return data
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse {TRADES_FILE}: {e}")
        raise


def save_trades(trades: dict) -> None:
    """Save trade log to paper_trades.json (pretty-printed)."""
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2, default=str)
    log.info(f"Saved {len(trades)} trades to {TRADES_FILE}")


def generate_trade_id() -> str:
    """Generate a short unique trade ID like 'PT-A3F2'."""
    return "PT-" + str(uuid.uuid4()).upper()[:6]


def cmd_entry(args, trades: dict) -> dict:
    """
    Record a new paper trade entry.

    Reads setup JSON from --setup arg or from stdin (generate_signal.py output).
    """
    setup = None

    if args.setup:
        try:
            setup = json.loads(args.setup)
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse --setup JSON: {e}")
            sys.exit(1)
    elif not sys.stdin.isatty():
        # Read from stdin (piped from generate_signal.py)
        raw = sys.stdin.read().strip()
        if raw:
            try:
                signal = json.loads(raw)
                # Accept either full signal output or just the setup block
                if "setup" in signal:
                    setup = signal["setup"]
                else:
                    setup = signal
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse stdin JSON: {e}")
                sys.exit(1)

    if setup is None:
        log.error("No setup provided. Use --setup JSON or pipe from generate_signal.py")
        sys.exit(1)

    now_et = datetime.now(ET)
    trade_id = generate_trade_id()

    # Mandatory setup fields with safe fallback
    trade = {
        "trade_id": trade_id,
        "status": "open",
        "entry_time": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "exit_time": None,
        "short_call": setup.get("short_call"),
        "long_call": setup.get("long_call"),
        "short_put": setup.get("short_put"),
        "long_put": setup.get("long_put"),
        "wing_width": setup.get("wing_width"),
        "credit_target_low": setup.get("credit_target_low"),
        "credit_target_high": setup.get("credit_target_high"),
        "stop_per_side": setup.get("stop_per_side"),
        "profit_target_pct": setup.get("profit_target_pct", 50),
        "credit_received": args.credit_received if hasattr(args, "credit_received") and args.credit_received else None,
        "exit_credit": None,
        "pnl": None,
        "exit_reason": None,
        "notes": args.notes if hasattr(args, "notes") and args.notes else None,
    }

    trades[trade_id] = trade
    save_trades(trades)

    log.info(
        f"Entered paper trade {trade_id}: "
        f"IC {trade['short_put']}/{trade['long_put']} | {trade['short_call']}/{trade['long_call']}"
    )

    result = {
        "action": "entry",
        "trade_id": trade_id,
        "trade": trade,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return result


def cmd_exit(args, trades: dict) -> dict:
    """
    Record a paper trade exit. Updates the existing trade record.
    """
    trade_id = args.id
    if not trade_id:
        # If no ID given, close the most recently opened trade
        open_trades = [(tid, t) for tid, t in trades.items() if t.get("status") == "open"]
        if not open_trades:
            log.error("No open trades found and no --id specified")
            sys.exit(1)
        # Sort by entry_time descending, pick last opened
        open_trades.sort(key=lambda x: x[1].get("entry_time", ""), reverse=True)
        trade_id, _ = open_trades[0]
        log.info(f"No --id specified. Closing most recent open trade: {trade_id}")

    if trade_id not in trades:
        log.error(f"Trade ID '{trade_id}' not found in paper_trades.json")
        sys.exit(1)

    trade = trades[trade_id]
    if trade.get("status") != "open":
        log.warning(f"Trade {trade_id} is already {trade['status']}. Overwriting exit data.")

    now_et = datetime.now(ET)
    exit_credit = args.exit_credit if hasattr(args, "exit_credit") and args.exit_credit is not None else 0.0
    credit_received = (
        trade.get("credit_received")
        or (args.credit_received if hasattr(args, "credit_received") and args.credit_received else None)
    )

    # P&L calculation: (credit received - exit credit) per spread
    # Positive P&L = profit
    pnl = None
    if credit_received is not None:
        pnl = round(float(credit_received) - float(exit_credit), 2)

    trade["status"] = "closed"
    trade["exit_time"] = now_et.strftime("%Y-%m-%dT%H:%M:%S")
    trade["exit_credit"] = exit_credit
    trade["pnl"] = pnl
    trade["exit_reason"] = args.reason if hasattr(args, "reason") and args.reason else "manual"
    if hasattr(args, "notes") and args.notes:
        trade["notes"] = args.notes
    if credit_received is not None and trade.get("credit_received") is None:
        trade["credit_received"] = credit_received

    trades[trade_id] = trade
    save_trades(trades)

    log.info(f"Closed paper trade {trade_id}: pnl={pnl}, reason={trade['exit_reason']}")

    result = {
        "action": "exit",
        "trade_id": trade_id,
        "trade": trade,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return result


def cmd_list(trades: dict) -> dict:
    """List all open paper trades."""
    open_trades = {tid: t for tid, t in trades.items() if t.get("status") == "open"}
    log.info(f"Open trades: {len(open_trades)}")

    result = {
        "action": "list",
        "open_count": len(open_trades),
        "total_count": len(trades),
        "open_trades": open_trades,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Sentinel paper trade logger")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--entry", action="store_true", help="Log a new trade entry")
    group.add_argument("--exit", action="store_true", help="Log a trade exit")
    group.add_argument("--list", action="store_true", help="List open trades")

    parser.add_argument("--id", default=None, help="Trade ID (for --exit)")
    parser.add_argument("--setup", default=None, help="JSON setup block (for --entry)")
    parser.add_argument(
        "--credit-received", type=float, default=None,
        help="Total credit received per spread at entry (e.g. 1.75)"
    )
    parser.add_argument(
        "--exit-credit", type=float, default=0.0,
        help="Credit paid to close at exit (e.g. 0.85); use 0 for expired worthless"
    )
    parser.add_argument("--reason", default="manual", help="Exit reason (profit_target|stop_loss|force_close|manual)")
    parser.add_argument("--notes", default=None, help="Free-text notes")
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        trades = load_trades()
    except Exception as e:
        log.error(f"Could not load trades: {e}")
        sys.exit(1)

    if args.entry:
        result = cmd_entry(args, trades)
    elif args.exit:
        result = cmd_exit(args, trades)
    elif args.list:
        result = cmd_list(trades)
    else:
        log.error("Unknown command")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
