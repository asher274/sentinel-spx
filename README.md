# Sentinel

**Automated SPX 0DTE Iron Condor Trading System**

Sentinel is a disciplined, rules-based system for trading SPX 0DTE iron condors. It combines multi-factor signal generation, automated paper trading, and a phased path to live execution — all governed by strict circuit breakers and human oversight.

---

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | Full technical reference — agent stack, scripts, infrastructure, data flow |
| [Phase 0 — Paper Trading](docs/phase-0-paper.md) | Current operating phase — signal generation and paper trade logging |
| [Phase 1 — Alerts Only](docs/phase-1-alerts.md) | Alert-only mode — signal posting without execution |
| [Phase 2 — Automated Trading](docs/phase-2-automated.md) | Future live trading via IBKR — reference only, not yet active |

---

## Current Phase

**Phase 0 — Paper Trading**

Sentinel is generating live signals and logging paper trades. Phase 0 exit criteria: 50+ trades, 30-day run, 55–65% win rate, 10+ daily reports, zero unhandled errors for 5 consecutive days, and explicit approval to proceed.

---

## System Overview

```
Pre-Market (9:00 AM ET)
  perplexity_scan.py   → macro risk assessment
  uw_flow_scan.py      → SPX/SPY unusual options flow
  check_vix.py         → VIX regime classification
  check_gex.py         → gamma exposure walls
  check_calendar.py    → event risk filter

Signal Window (9:30–10:30 AM ET)
  generate_signal.py   → composite GO / NO-TRADE decision
  format_alert.py      → Discord-ready alert formatting
  paper_trade.py       → paper trade entry logging

Trade Management
  paper_trade.py --exit → exit logging with P&L
  daily_report.py       → end-of-day summary

Infrastructure
  OpenClaw (AI layer) · Redis (state) · PostgreSQL (persistence)
  Prometheus + Grafana (monitoring) · Docker (containerization)
```

---

## Repository Structure

```
sentinel/
  openclaw/          AI agent workspace (AGENTS.md, MEMORY.md, anchor.md)
  scripts/           Python signal + execution scripts
  docs/              Architecture and phase documentation
  docker/            Container configuration
```

---

*Private system. Not financial advice.*
