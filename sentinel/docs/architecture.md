# Sentinel — System Architecture

> **Version:** Phase 0 (Paper Trading)  
> **Last Updated:** 2026-03-04  
> **Status:** Operational — Paper Mode

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Agent Stack](#2-agent-stack)
3. [Script Inventory](#3-script-inventory)
4. [Signal Pipeline & Data Flow](#4-signal-pipeline--data-flow)
5. [Infrastructure](#5-infrastructure)
6. [Environment Variables](#6-environment-variables)
7. [Phase Definitions](#7-phase-definitions)
8. [Circuit Breaker Mechanics](#8-circuit-breaker-mechanics)
9. [Kill Switch Protocol](#9-kill-switch-protocol)
10. [Scheduling](#10-scheduling)
11. [Monitoring & Observability](#11-monitoring--observability)
12. [Security Notes](#12-security-notes)

---

## 1. System Overview

Sentinel is a disciplined, data-driven 0DTE SPX iron condor trading agent. It operates on a three-phase model:

- **Phase 0 (Paper Trading):** Fully autonomous simulation. No real money. Validates signal quality and system reliability over 30+ days and 50+ trades before advancing.
- **Phase 1 (Alerts Only):** Bot identifies setups and posts rich Discord alerts. Human executes manually.
- **Phase 2 (Automated Execution):** Live IBKR execution. Starts at quarter size, scales after validation.

The system is self-hosted on a Hetzner VPS and managed via the OpenClaw AI agent framework. All decisions are logged, auditable, and reversible. No order is placed without explicit circuit breaker clearance.

### Core Trading Strategy

| Parameter | Value |
|-----------|-------|
| Underlying | SPX (not SPXW, not SPY) — Section 1256 tax treatment |
| Strategy | 0DTE Iron Condor |
| Trading Days | Monday / Tuesday / Thursday |
| Short Strike Target | 8–12 delta |
| Wing Width | 20–30 points (widens 5pt in elevated VIX) |
| Entry Window | 10:05–10:35 AM ET |
| Profit Target | 50% of credit received |
| Stop Loss | Per-side loss = total IC credit (breakeven IC rule) |
| Force Close | 3:45 PM ET daily |
| Size (Phase 0/1) | Paper / 0 contracts |
| Size (Phase 2 Start) | Quarter size |
| Size (Phase 2 Scale) | Full size after 20 live winning trades |

---

## 2. Agent Stack

Sentinel runs inside the OpenClaw AI agent framework. The agent is composed of the following layers:

### 2.1 OpenClaw Runtime

OpenClaw provides:
- Persistent memory across sessions (`openclaw/MEMORY.md`)
- Compaction-resistant anchor rules (`openclaw/anchor.md`)
- Context buffer for cross-session state (`openclaw/system/context-buffer.md`)
- Discord command interface via bot token
- Sub-agent spawning for audits, reports, and background tasks

### 2.2 Sentinel Agent Identity

| File | Purpose |
|------|---------|
| `openclaw/SOUL.md` | Sentinel's identity, trading philosophy, and operating principles |
| `openclaw/AGENTS.md` | Operating manual — rules for autonomous operation |
| `openclaw/anchor.md` | Immutable rules that survive context compaction |
| `openclaw/MEMORY.md` | Long-term memory: past trades, system state, key decisions |
| `openclaw/system/context-buffer.md` | Cross-session state template |

### 2.3 Signal Layer

Four overlapping external data sources feed into signal generation:

| Source | Provider | Purpose | Script |
|--------|----------|---------|--------|
| Options Chain + GEX | Polygon.io (Advanced plan) | Real-time SPX Greeks, GEX calculation | `check_gex.py` |
| Volatility Regime | FRED API + Polygon fallback | VIX fetch and regime classification | `check_vix.py` |
| Economic Calendar | Hardcoded (2026 FOMC/CPI/NFP) | Block entries near high-impact events | `check_calendar.py` |
| Macro Prediction Markets | Polymarket Gamma API | Contrarian macro risk overlay | `polymarket_scan.py` |
| Pre-market News | Perplexity Sonar API | Overnight news scan, risk classification | `perplexity_scan.py` |
| Options Flow | Unusual Whales API | Institutional flow, dark pool prints | `uw_flow_scan.py` |

No single signal source is decisive. **All layers must align** before a GO decision is issued.

---

## 3. Script Inventory

All scripts live in `scripts/`. They follow a consistent pattern:
- Shebang: `#!/usr/bin/env python3`
- JSON to stdout
- Logging to stderr
- Environment loaded from `../.env.trading` via python-dotenv

### 3.1 Filter Scripts (run by `generate_signal.py`)

| Script | Purpose | Primary API | Key Output Fields |
|--------|---------|------------|-------------------|
| `check_vix.py` | Fetch VIX, classify volatility regime | FRED (primary), Polygon (fallback) | `vix`, `regime`, `trading_allowed` |
| `check_calendar.py` | Check for FOMC/CPI/NFP blocking events | Hardcoded 2026 dates | `safe_to_trade`, `events_today`, `blocking_in_30min` |
| `check_gex.py` | Calculate SPX 0DTE GEX, find walls | Polygon Advanced | `gex_regime`, `call_wall`, `put_wall`, `zero_gamma` |
| `polymarket_scan.py` | Macro risk overlay from prediction markets | Polymarket Gamma (public) | `macro_risk_signal`, `markets`, `relevant_count` |

### 3.2 Pre-market Scan Scripts

| Script | Purpose | Primary API | Key Output Fields |
|--------|---------|------------|-------------------|
| `perplexity_scan.py` | Overnight macro news, risk classification | Perplexity Sonar | `summary`, `risk_level`, `headlines` |
| `uw_flow_scan.py` | SPX/SPY options flow last 2h | Unusual Whales | `flow_signal`, `large_prints`, `spx_net_delta` |

### 3.3 Signal Generation

| Script | Purpose | Inputs | Key Output Fields |
|--------|---------|--------|-------------------|
| `generate_signal.py` | Master synthesizer — runs all filters, issues GO/NO_TRADE | Runs subprocesses for all filter scripts | `decision`, `setup`, `filters`, `confidence` |

### 3.4 Operations Scripts

| Script | Purpose | Inputs | Key Output Fields |
|--------|---------|--------|-------------------|
| `format_alert.py` | Format GO/NO_TRADE signal as Discord alert | JSON from `generate_signal.py` via stdin | `alert_text`, `summary_line` |
| `paper_trade.py` | Paper trade logger — entry and exit tracking | CLI args (`--entry`/`--exit`) | `action`, `trade_id`, `trade` |
| `daily_report.py` | End-of-day P&L and performance report | `paper_trades.json` + `MEMORY.md` | `daily_pnl`, `win_rate`, `report_text` |

### 3.5 Phase 2 Scripts (Not Yet Active)

| Script | Purpose | Status |
|--------|---------|--------|
| `ibkr_place_ic.py` | Place iron condor order via IBKR API | Phase 2 only — DO NOT RUN |
| `ibkr_close_all.py` | Emergency close all open IBKR positions | Phase 2 only — DO NOT RUN |

---

## 4. Signal Pipeline & Data Flow

### 4.1 Pre-market Flow (9:00 AM ET)

```
[Scheduler / Cron / OpenClaw]
        |
        v
perplexity_scan.py  ──> JSON: {summary, risk_level, headlines}
uw_flow_scan.py     ──> JSON: {flow_signal, large_prints, spx_net_delta}
        |
        v
[Agent reads outputs, stores in session context]
[If risk_level == "high": optionally skip entry analysis]
```

### 4.2 Entry Analysis Flow (10:05–10:35 AM ET)

```
[Scheduler / Agent Command]
        |
        v
generate_signal.py
  ├── check_vix.py       (Filter 1: VIX regime)
  ├── check_calendar.py  (Filter 2: Economic calendar)
  ├── check_gex.py       (Filter 3: GEX regime + walls)
  └── polymarket_scan.py (Filter 4: Macro risk overlay)
        |
   [All pass?]
   YES                   NO
    |                     |
    v                     v
  build_setup()      NO_TRADE result
    |
    v
JSON: {decision: "GO", setup: {...}, filters: {...}, confidence: float}
        |
        v
format_alert.py   (pipe: generate_signal.py | format_alert.py)
        |
        v
JSON: {alert_text, summary_line}
        |
        v
[Post to Discord #signals]
[paper_trade.py --entry if Phase 0]
```

### 4.3 Filter Decision Logic

Each filter can `pass`, `fail`, or `warn`. A single `fail` stops the pipeline immediately. Only a `warn` (from Polymarket medium risk) reduces confidence but does not block.

```
Filter 1: Day of Week
  PASS → Mon, Tue, Thu only
  FAIL → Wed, Fri, weekend

Filter 2: Time Window
  PASS → 10:05 AM to 10:35 AM ET
  FAIL → Any time outside window

Filter 3: VIX
  PASS → VIX < 30 (trading_allowed = True)
  FAIL → VIX >= 30 (Strategy Alpha halted)
  WARN → VIX 25–30 (half size, confidence penalty)

Filter 4: Calendar
  PASS → No blocking events, not within 30min of release
  FAIL → FOMC/CPI/NFP active or imminent

Filter 5: GEX
  PASS → gex_regime == "positive"
  FAIL → gex_regime == "negative" (dealer hedging adverse)

Filter 6: Polymarket
  PASS → macro_risk_signal == "low" or "unknown"
  WARN → macro_risk_signal == "medium" (confidence -= 0.1)
  FAIL → macro_risk_signal == "high"
```

### 4.4 Setup Construction

When all filters pass, `generate_signal.py` constructs the iron condor setup:

```python
short_call = call_wall + 10       # 10 points above GEX call wall
short_put  = put_wall  - 10       # 10 points below GEX put wall
long_call  = short_call + wing_width
long_put   = short_put  - wing_width
# Wing width: BASE_WING_WIDTH=25, +5pt if VIX elevated
```

Credit targets and stops are hardcoded in `generate_signal.py`:
- `CREDIT_TARGET_LOW = 1.50`
- `CREDIT_TARGET_HIGH = 2.50`
- `PROFIT_TARGET_PCT = 50`

### 4.5 End-of-Day Flow (4:00 PM ET)

```
[Scheduler / Agent Command]
        |
        v
[Force close any open trades: paper_trade.py --exit --reason force_close]
        |
        v
daily_report.py
  ├── reads paper_trades.json  (today's entries/exits)
  └── reads openclaw/MEMORY.md (session notes)
        |
        v
JSON: {date, day_type, daily_pnl, win_rate, report_text, ...}
        |
        v
[Post to Discord #daily-report]
[Agent saves session memory]
```

---

## 5. Infrastructure

### 5.1 VPS

| Property | Value |
|----------|-------|
| Provider | Hetzner Cloud |
| Instance | CCX23 (4 dedicated vCPU, 16 GB RAM) |
| Region | Ashburn, VA (us-east proximity to CBOE/Polygon servers) |
| OS | Ubuntu 22.04 LTS |
| Storage | 160 GB NVMe SSD |

### 5.2 Docker Stack

All services run under the `sentinel` Docker Compose project. Network: `sentinel-net` (external bridge).

| Container | Image | Port Binding | Purpose |
|-----------|-------|-------------|---------|
| `openclaw-gateway` | openclaw/gateway | — | OpenClaw bot runtime |
| `sentinel-postgres` | postgres:16 | 127.0.0.1:5433→5432 | Trade logs, strategy state, config |
| `sentinel-redis` | redis:7-alpine | 127.0.0.1:6380→6379 | Circuit breaker state, kill switch, pub/sub |
| `sentinel-grafana` | grafana/grafana-oss | 0.0.0.0:3001→3000 | Monitoring dashboards (Phase 1+) |
| `sentinel-prometheus` | prom/prometheus | 127.0.0.1:9091→9090 | Metrics collection (Phase 1+) |
| `ib-gateway` | ib-gateway (custom) | 127.0.0.1:4002→4002 | IBKR headless connection (Phase 2 only) |

**Note:** Grafana is publicly accessible on port 3001. Protect with a firewall rule or reverse proxy + auth in production.

### 5.3 Port Summary

| Port | Service | Binding | Notes |
|------|---------|---------|-------|
| 5433 | PostgreSQL | localhost only | Mapped from container 5432 |
| 6380 | Redis | localhost only | Mapped from container 6379 |
| 3001 | Grafana | 0.0.0.0 (public) | Password protect externally |
| 9091 | Prometheus | localhost only | Internal scraping only |
| 4002 | IB Gateway (paper) | localhost only | Phase 2 only |
| 4001 | IB Gateway (live) | localhost only | Phase 2 live only |

### 5.4 Docker Compose Files

| File | Purpose |
|------|---------|
| `docker/docker-compose.yml` | Core stack (Phase 0 and 1) |
| `docker/docker-compose.phase2.yml` | Adds IB Gateway service |
| `docker/prometheus.yml` | Prometheus scrape config |
| `docker/.env.example` | Template for all env vars |

### 5.5 Data Persistence

| Volume | Container | Purpose |
|--------|-----------|---------|
| `sentinel-postgres-data` | postgres | All trade records and config |
| `sentinel-redis-data` | redis | Circuit breaker state (persisted with AOF) |
| `sentinel-grafana-data` | grafana | Dashboard configs |
| `sentinel-prometheus-data` | prometheus | 30-day metrics retention |

---

## 6. Environment Variables

All variables sourced from `.env.trading` (in project root) via `python-dotenv`.  
Docker services use `docker/.env` (copy of `.env.example` with values filled in).

### 6.1 Database

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_PASSWORD` | Yes | Postgres password (min 32 chars random) |
| `DB_HOST` | Yes | Database host (default: `localhost`) |
| `DB_PORT` | Yes | Database port (default: `5433`) |
| `DB_NAME` | Yes | Database name (default: `sentinel`) |
| `DB_USER` | Yes | Database user (default: `sentinel`) |

### 6.2 Redis

| Variable | Required | Description |
|----------|----------|-------------|
| `REDIS_PASSWORD` | Yes | Redis auth password (min 32 chars random) |
| `REDIS_HOST` | Yes | Redis host (default: `localhost`) |
| `REDIS_PORT` | Yes | Redis port (default: `6380`) |

### 6.3 Market Data APIs

| Variable | Required | Description | Cost |
|----------|----------|-------------|------|
| `POLYGON_API_KEY` | Yes | Polygon.io — Advanced plan | $199/mo |
| `FRED_API_KEY` | Yes | FRED (free) — VIX data | Free |
| `UNUSUAL_WHALES_API_KEY` | Yes | Unusual Whales flow scanner | $48/mo |
| `PERPLEXITY_API_KEY` | Yes | Perplexity Sonar — pre-market news | ~$50/mo |

### 6.4 Notifications

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | Discord bot token |
| `DISCORD_COMMAND_CHANNEL_ID` | Yes | #sentinel-command |
| `DISCORD_SIGNAL_CHANNEL_ID` | Yes | #signals — trade signals |
| `DISCORD_ALERTS_CHANNEL_ID` | Yes | #alerts — risk/system warnings |
| `DISCORD_PAPER_CHANNEL_ID` | Phase 0 | #paper-trades — paper activity |
| `DISCORD_REPORT_CHANNEL_ID` | Yes | #daily-report |
| `DISCORD_HEALTH_CHANNEL_ID` | Yes | #sentinel-health |
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram fallback notifications |
| `TELEGRAM_CHAT_ID` | Optional | Personal Telegram chat ID |

### 6.5 AI / OpenClaw

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for agent reasoning |

### 6.6 IBKR (Phase 2 Only)

| Variable | Required | Description |
|----------|----------|-------------|
| `IBKR_USERNAME` | Phase 2 | IBKR paper trading username |
| `IBKR_PASSWORD` | Phase 2 | IBKR paper trading password |
| `IBKR_LIVE_USERNAME` | Phase 2 Live | IBKR live username — DO NOT SET until ready |
| `IBKR_LIVE_PASSWORD` | Phase 2 Live | IBKR live password |
| `IBKR_TRADING_MODE` | Phase 2 | `paper` or `live` |
| `IBKR_PORT` | Phase 2 | `4002` for paper, `4001` for live |
| `VNC_PASSWORD` | Phase 2 | IB Gateway VNC debug access |

### 6.7 System

| Variable | Required | Description |
|----------|----------|-------------|
| `GRAFANA_PASSWORD` | Yes | Grafana admin password |
| `SENTINEL_PHASE` | Yes | Current phase: `0`, `1`, or `2` |

---

## 7. Phase Definitions

### Phase 0 — Paper Trading

**Status:** ACTIVE (current phase)

- Fully autonomous paper trading simulation
- All signals generated and formatted
- Trades logged to `paper_trades.json` via `paper_trade.py`
- No real money, no IBKR connection
- Daily reports generated and posted to Discord
- Goal: validate signal quality and system reliability

**Entry Criteria:** System deployed, all APIs connected, at least 1 successful test run of `generate_signal.py`

**Exit Criteria (all must be met):**
1. ≥ 50 paper trades logged
2. ≥ 30 calendar days of operation
3. Win rate 55–65% sustained (or above 65% consistently)
4. Zero system errors for 5 consecutive trading days
5. Daily reports generated for ≥ 10 trading days
6. Explicit approval from the operator

See `docs/phase-0-paper.md` for full details.

---

### Phase 1 — Alerts Only

**Status:** FUTURE (not yet active)

- Bot posts signals to Discord #signals channel
- Human (the operator) executes trades manually
- Theoretical P&L tracked in paper_trades.json
- System measures human execution confirmation rate

**Exit Criteria:**
1. Phase 0 criteria met and approved
2. ≥ 20 alert cycles observed and manually executed
3. Real P&L tracking confirms signal quality
4. Explicit approval from the operator

See `docs/phase-1-alerts.md` for full details.

---

### Phase 2 — Automated Execution

**Status:** FUTURE (not yet active)

- Live IBKR integration via `ib_insync`
- Starts at quarter size (1 contract per side)
- Scales to half size after 10 profitable trades
- Scales to full size after 20 profitable trades
- Phase 1 alerts continue as transparency layer

**WARNING:** Phase 2 requires explicit activation with `SENTINEL_PHASE=2` and must never be enabled without the operator's explicit go-ahead.

See `docs/phase-2-automated.md` for full details.

---

## 8. Circuit Breaker Mechanics

Circuit breakers are the primary risk control layer. They run independently of signal generation. In Phase 0, circuit breakers are simulated (no real money). In Phase 2, they control live order flow.

### 8.1 Circuit Breaker States

Circuit breaker states are stored in Redis with persistent AOF. Keys:

| Redis Key | Value | Meaning |
|-----------|-------|---------|
| `cb:strategy_alpha:halted` | `0` or `1` | Strategy Alpha (SPX IC) halted |
| `cb:all_trading:halted` | `0` or `1` | All trading halted |
| `cb:size_reduction:active` | `0` or `1` | 50% size reduction active |
| `cb:kill_switch` | `0` or `1` | Emergency kill switch (hard halt) |
| `cb:daily_loss:strategy_alpha` | float | Today's Strategy Alpha P&L |
| `cb:daily_loss:total` | float | Today's total P&L |
| `cb:weekly_loss` | float | This week's total P&L |
| `cb:monthly_loss` | float | This month's total P&L |

### 8.2 Trigger Table

| Trigger | Condition | Action |
|---------|-----------|--------|
| Daily loss — Strategy Alpha | Loss > 3% of account | Halt Strategy Alpha for the day |
| Daily loss — Combined | Loss > 4% of account | Halt all trading for the day |
| Weekly loss | Loss > 5% of account | Reduce all position sizes 50% |
| Monthly loss — Alpha | Loss > 8% of account | Halt Strategy Alpha, require manual review |
| Monthly loss — All | Loss > 10% of account | Halt everything, require manual review |
| VIX spike | VIX ≥ 30 | Halt Strategy Alpha (auto-detected by check_vix.py) |
| VIX extreme | VIX ≥ 45 | Halt everything |
| Drawdown — Peak | Loss ≥ 35% from equity peak | Close all positions, full system halt |
| Error threshold | 3+ consecutive script failures | Alert, optionally halt |

### 8.3 Circuit Breaker Reset

- **Daily** circuit breakers reset at midnight ET automatically
- **Weekly** resets happen Monday morning
- **Monthly** resets happen 1st of month
- **Manual override** via Discord `/kill` command or Redis `SET cb:strategy_alpha:halted 0`
- **Drawdown halt** requires manual review and explicit Redis reset

### 8.4 Checking Circuit Breaker State

Before any order is placed (Phase 2), the order function must check:

```python
import redis
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)

if r.get("cb:kill_switch") == b"1":
    raise RuntimeError("Kill switch active — trading halted")
if r.get("cb:all_trading:halted") == b"1":
    raise RuntimeError("All trading halted by circuit breaker")
if r.get("cb:strategy_alpha:halted") == b"1":
    raise RuntimeError("Strategy Alpha halted by circuit breaker")
```

---

## 9. Kill Switch Protocol

The kill switch is the last line of defense. It is a Redis flag (`cb:kill_switch = 1`) that blocks all order placement, position management, and signal execution.

### 9.1 Activating the Kill Switch

**Via Discord command:**
```
/kill
```
This command:
1. Sets `cb:kill_switch = 1` in Redis
2. If Phase 2 is active: calls `ibkr_close_all.py` to close all open positions
3. Posts confirmation to #alerts channel
4. Logs the action to MEMORY.md

**Via Redis CLI (emergency):**
```bash
redis-cli -h localhost -p 6380 -a $REDIS_PASSWORD SET cb:kill_switch 1
```

### 9.2 What the Kill Switch Stops

- All new order placement (Phase 2)
- All position management (Phase 2)
- Signal generation (skips if kill switch is active)
- Paper trade logging (can optionally bypass for auditing)

### 9.3 Resetting the Kill Switch

The kill switch **never resets automatically**. It requires explicit human action:

```bash
# Via Redis CLI
redis-cli -h localhost -p 6380 -a $REDIS_PASSWORD SET cb:kill_switch 0

# Via Discord (future command)
/resume
```

Before resetting, verify:
1. Root cause of activation identified
2. Any open positions closed or accounted for
3. the operator explicitly approves resumption
4. System health check passed

### 9.4 Force Close Protocol

When the kill switch is activated with open positions (Phase 2):

1. `ibkr_close_all.py` runs immediately
2. It sends MKT orders to close all open SPX iron condors
3. Retries up to 3 times on failure
4. Posts confirmation of each close to #alerts
5. If all closes fail after retries: pages the operator via Telegram

---

## 10. Scheduling

Sentinel runs on a schedule managed by OpenClaw's cron system or system cron.

### 10.1 Daily Schedule (ET)

| Time | Action | Script / Command |
|------|--------|-----------------|
| 8:55 AM | Pre-market scan | `perplexity_scan.py` + `uw_flow_scan.py` |
| 9:00 AM | Agent wakes, reads pre-market context | OpenClaw session start |
| 10:05 AM | Entry analysis begins | `generate_signal.py` |
| 10:05–10:35 AM | Signal window | `generate_signal.py` (runs until GO or window closes) |
| 10:35 AM | Entry window closes | NO_TRADE if no GO by now |
| 3:45 PM | Force close all open positions | `paper_trade.py --exit --reason force_close` (Phase 0) |
| 4:00 PM | Daily report | `daily_report.py` |
| 4:05 PM | Post report to Discord | OpenClaw posts `report_text` to #daily-report |
| 4:10 PM | Save session memory | `/save` command |

### 10.2 Non-Trading Days

On Wednesday, Friday, and weekends:
- Pre-market scan still runs (for awareness)
- `generate_signal.py` will issue NO_TRADE due to day-of-week filter
- Daily report still runs (shows zero trades entered)

---

## 11. Monitoring & Observability

### 11.1 Discord Channels

| Channel | Purpose |
|---------|---------|
| `#sentinel-command` | Human commands to bot |
| `#signals` | GO/NO_TRADE alerts |
| `#alerts` | Risk warnings, circuit breaker events |
| `#paper-trades` | Phase 0 paper trade entries/exits |
| `#daily-report` | End-of-day P&L summaries |
| `#sentinel-health` | System health, uptime, API status |

### 11.2 Grafana Dashboards (Phase 1+)

Grafana runs at `http://<VPS_IP>:3001` (admin / `$GRAFANA_PASSWORD`).

Planned dashboards:
- **Signal Performance:** GO rate, filter pass rates, confidence distribution
- **P&L Tracker:** Daily/weekly/monthly P&L, win rate trend
- **API Health:** Response times and error rates for all external APIs
- **Circuit Breaker State:** Current CB states, trigger history

### 11.3 Prometheus Metrics (Phase 1+)

Prometheus scrapes at `http://localhost:9091`. Retention: 30 days.

Key metrics to expose:
- `sentinel_signals_total{decision="GO|NO_TRADE", reason="..."}`
- `sentinel_filter_pass_total{filter="vix|calendar|gex|polymarket"}`
- `sentinel_api_latency_seconds{api="polygon|fred|uw|perplexity"}`
- `sentinel_circuit_breaker_state{name="strategy_alpha|all_trading"}`
- `sentinel_paper_pnl_total`

### 11.4 Logging

All scripts log to stderr with timestamps and script name prefix:

```
2026-03-04T09:15:32 [check_vix] INFO Fetching VIX from FRED...
2026-03-04T09:15:33 [check_vix] INFO VIX from FRED: 18.42
2026-03-04T09:15:33 [check_vix] INFO Regime: normal, size_multiplier: 1.0, trading_allowed: True
```

In production, stderr is captured by Docker logging driver and can be shipped to Loki + Grafana.

---

## 12. Security Notes

- `.env.trading` and `docker/.env` must never be committed to version control (`.gitignore` enforced)
- Postgres and Redis are bound to `127.0.0.1` only — never expose to 0.0.0.0
- Grafana is the only service with a public port — protect with a firewall rule allowing only known IPs, or add nginx basic auth
- API keys should be rotated if the VPS is ever compromised
- IBKR live credentials must never be set until explicitly approved by the operator
- The kill switch requires Redis auth — don't share `REDIS_PASSWORD`
- All SSH access to VPS should use key-based auth only (no passwords)

---

*End of Architecture Document*
