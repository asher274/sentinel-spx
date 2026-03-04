---
title: Sentinel — SPX 0DTE Iron Condor System
layout: home
nav_order: 1
---

# Sentinel

**Automated SPX 0DTE Iron Condor Trading System**

Sentinel is a disciplined, rules-based system for trading SPX 0DTE iron condors. Multi-factor signal generation, automated paper trading, and a phased path to live execution — governed by strict circuit breakers and human oversight.

---

## Current Phase: Paper Trading (Phase 0)

Signal generation active. Paper trades logged daily. Exit criteria: 50+ trades, 30-day run, 55–65% win rate, 10+ daily reports, zero unhandled errors for 5 days, explicit approval to proceed.

---

## Documentation

- [Architecture](architecture) — Technical reference, agent stack, scripts, infrastructure
- [Phase 0 — Paper Trading](phase-0-paper) — Current operating guide
- [Phase 1 — Alerts Only](phase-1-alerts) — Alert-only mode documentation
- [Phase 2 — Automated Trading](phase-2-automated) — Future live execution reference

---

## Signal Pipeline

| Time (ET) | Script | Output |
|---|---|---|
| 9:00 AM | `perplexity_scan.py` | Macro risk level |
| 9:00 AM | `uw_flow_scan.py` | Flow signal |
| 9:00 AM | `check_vix.py` | VIX regime |
| 9:00 AM | `check_gex.py` | GEX walls |
| 9:00 AM | `check_calendar.py` | Event risk |
| 9:30–10:30 AM | `generate_signal.py` | GO / NO-TRADE |
| On GO | `format_alert.py` | Discord alert |
| On GO | `paper_trade.py` | Paper entry |
| 4:30 PM | `daily_report.py` | Daily summary |

*Not financial advice.*
