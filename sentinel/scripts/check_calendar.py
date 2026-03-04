#!/usr/bin/env python3
"""
check_calendar.py — Check for high-impact economic events that block trading.

Hardcoded 2026 event dates:
  - FOMC: Jan 28-29, Mar 18-19, May 6-7, Jun 17-18, Jul 29-30, Sep 16-17, Nov 4-5, Dec 9-10
  - CPI: ~2nd Tuesday of each month, 8:30am ET
  - NFP: 1st Friday of each month, 8:30am ET

Blocking window: 30 minutes before event time, until end of day.

Output JSON to stdout. Logging to stderr.
"""

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta

import pytz
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.trading"))

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [check_calendar] %(levelname)s %(message)s",
)
log = logging.getLogger("check_calendar")

ET = pytz.timezone("America/New_York")

# --- Hardcoded FOMC dates (both days of each meeting) ---
FOMC_DATES_2026 = {
    date(2026, 1, 28), date(2026, 1, 29),
    date(2026, 3, 18), date(2026, 3, 19),
    date(2026, 5, 6),  date(2026, 5, 7),
    date(2026, 6, 17), date(2026, 6, 18),
    date(2026, 7, 29), date(2026, 7, 30),
    date(2026, 9, 16), date(2026, 9, 17),
    date(2026, 11, 4), date(2026, 11, 5),
    date(2026, 12, 9), date(2026, 12, 10),
}
FOMC_DECISION_TIME = (14, 0)  # 2:00 PM ET (decision day, day 2)
# Day-1 of FOMC (no announcement): still block as precaution
FOMC_DAY2_DATES = {
    date(2026, 1, 29),
    date(2026, 3, 19),
    date(2026, 5, 7),
    date(2026, 6, 18),
    date(2026, 7, 30),
    date(2026, 9, 17),
    date(2026, 11, 5),
    date(2026, 12, 10),
}


def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of weekday (0=Mon) in the given month."""
    first = date(year, month, 1)
    # How many days until the first occurrence of weekday?
    days_ahead = weekday - first.weekday()
    if days_ahead < 0:
        days_ahead += 7
    first_occurrence = first + timedelta(days=days_ahead)
    return first_occurrence + timedelta(weeks=n - 1)


def compute_cpi_dates(year: int) -> set:
    """2nd Tuesday of each month."""
    dates = set()
    for month in range(1, 13):
        try:
            d = nth_weekday_of_month(year, month, 1, 2)  # Tuesday = 1
            dates.add(d)
        except ValueError:
            pass
    return dates


def compute_nfp_dates(year: int) -> set:
    """1st Friday of each month."""
    dates = set()
    for month in range(1, 13):
        try:
            d = nth_weekday_of_month(year, month, 4, 1)  # Friday = 4
            dates.add(d)
        except ValueError:
            pass
    return dates


def get_events_for_date(check_date: date) -> list[dict]:
    """Return list of events on check_date."""
    year = check_date.year
    cpi_dates = compute_cpi_dates(year)
    nfp_dates = compute_nfp_dates(year)

    events = []

    if check_date in FOMC_DATES_2026:
        if check_date in FOMC_DAY2_DATES:
            events.append({"name": "FOMC Decision", "time": "14:00 ET", "hour": 14, "minute": 0})
        else:
            # Day 1 — no specific time trigger but still mark as FOMC day
            events.append({"name": "FOMC Day 1", "time": "All Day", "hour": None, "minute": None})

    if check_date in cpi_dates:
        events.append({"name": "CPI Release", "time": "08:30 ET", "hour": 8, "minute": 30})

    if check_date in nfp_dates:
        events.append({"name": "NFP Release", "time": "08:30 ET", "hour": 8, "minute": 30})

    return events


def check_blocking(events: list[dict], now_et: datetime) -> tuple[bool, bool]:
    """
    Returns (blocking_event_active, blocking_in_30min).
    - active: current ET time is at or after event time (event already happened today)
    - in_30min: event is within the next 30 minutes
    """
    blocking_active = False
    blocking_in_30min = False

    for evt in events:
        hour = evt.get("hour")
        minute = evt.get("minute")

        if hour is None:
            # All-day block (FOMC Day 1) — block the whole day
            blocking_active = True
            continue

        event_time = now_et.replace(hour=hour, minute=minute, second=0, microsecond=0)
        minutes_until = (event_time - now_et).total_seconds() / 60

        if minutes_until <= 0:
            # Event already occurred today — still block
            blocking_active = True
        elif 0 < minutes_until <= 30:
            blocking_in_30min = True

    return blocking_active, blocking_in_30min


def main():
    now_et = datetime.now(ET)
    today = now_et.date()
    timestamp = now_et.strftime("%Y-%m-%dT%H:%M:%S")

    log.info(f"Checking calendar for {today} at {now_et.strftime('%H:%M ET')}")

    events = get_events_for_date(today)
    log.info(f"Events today: {[e['name'] for e in events]}")

    blocking_active, blocking_in_30min = check_blocking(events, now_et)

    safe_to_trade = not (blocking_active or blocking_in_30min)

    # Strip internal keys from output
    events_output = [{"name": e["name"], "time": e["time"]} for e in events]

    result = {
        "events_today": events_output,
        "blocking_event_active": blocking_active,
        "blocking_in_30min": blocking_in_30min,
        "safe_to_trade": safe_to_trade,
        "timestamp": timestamp,
    }

    log.info(f"safe_to_trade={safe_to_trade}")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
