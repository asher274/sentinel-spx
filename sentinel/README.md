# Sentinel

> A disciplined, data-driven 0DTE SPX iron condor trading agent built on [OpenClaw](https://openclaw.ai).

Sentinel monitors real-time options flow, macro conditions, and volatility regimes to identify high-probability 0DTE SPX iron condor setups. It runs on a self-hosted VPS, posts rich trade alerts to Discord, and can optionally execute autonomously via Interactive Brokers.

---

## What It Does

- **Pre-market scan** at 9:00 AM ET: synthesizes macro conditions, earnings context, economic calendar, and options flow via Perplexity Sonar + Unusual Whales
- **Entry analysis** at 10:15–10:30 AM ET: checks VIX regime, GEX, event calendar, and flow signals; generates a go/no-go decision with full setup parameters
- **Alerts** posted to Discord with strike prices, credit target, stop level, and signal rationale
- **Position management**: monitors profit target (50% of credit) and stop-loss; force-closes by 3:45 PM ET
- **End-of-day report**: P&L, signal accuracy, circuit breaker states

---

## Three Phases

| Phase | Mode | Description |
|-------|------|-------------|
| **Phase 0** | Paper Trading | 30-day autonomous simulation. No real money. Validates signal quality and system reliability. Requires 50+ trades and defined exit criteria before advancing. |
| **Phase 1** | Alerts Only | Bot identifies setups; human executes manually. Rich Discord alerts with full setup details. |
| **Phase 2** | Automated | Live execution via IBKR. Starts at quarter size, scales to full size after 20 live trades. Phase 1 alerts remain active as a transparency layer. |

---

## Signal Architecture

Sentinel uses four overlapping signal layers:

1. **Polygon.io Advanced** — Real-time SPX options chain, Greeks, GEX calculation, historical tick data
2. **Unusual Whales** — Options flow, dark pool prints, institutional positioning
3. **Polymarket** — Prediction market implied probabilities on macro events (contrarian overlay)
4. **Perplexity Sonar** — AI-powered real-time financial research and macro context

No single signal is decisive. All four must align before an entry is considered.

---

## Strategy: 0DTE SPX Iron Condors

**Core parameters:**

| Parameter | Value |
|-----------|-------|
| Underlying | SPX (not SPXW, not SPY) — Section 1256 tax treatment |
| Trading days | Mon / Tue / Thu only |
| Short strike delta | 8–12 delta |
| Wing width | 20–30 points |
| Entry window | 10:15–10:30 AM ET |
| Profit target | 50% of credit received |
| Stop loss | Per-side loss = total IC credit (breakeven IC rule) |
| Force close | 3:45 PM ET |

**VIX regime filters:**

| VIX Level | Action |
|-----------|--------|
| 14–25 | Full size |
| 25–30 | Half size |
| >30 | Halt Strategy Alpha |
| >45 | Halt everything |

**Additional filters:**
- GEX must be positive (positive gamma regime)
- No entries within 30 minutes of FOMC, CPI, or NFP releases
- Unusual Whales flow must not show significant directional positioning against the setup

---

## Circuit Breakers

| Trigger | Action |
|---------|--------|
| Daily loss 3% (Strategy Alpha) | Halt Strategy Alpha for the day |
| Daily loss 4% (combined) | Halt all trading for the day |
| Weekly loss 5% | Reduce all position sizes 50% |
| Monthly loss 8% | Halt Strategy Alpha, require manual review |
| Monthly loss 10% | Halt everything, require manual review |
| VIX >30 | Halt Strategy Alpha |
| VIX >45 | Halt everything |
| Drawdown 35% from peak | Close all positions, full system halt |

---

## Infrastructure

**VPS:** Hetzner CCX23 (4 dedicated vCPU, 16 GB RAM)

**Docker stack:**
- `openclaw-gateway` — bot runtime
- `postgres:16` — trade logs, strategy state, configuration
- `redis:7-alpine` — circuit breaker state, kill switch, pub/sub
- `grafana` — monitoring dashboards (Phase 1+)
- `prometheus` — metrics collection (Phase 1+)
- `ib-gateway` — IBKR headless connection (Phase 2 only)

---

## Monthly Cost Estimate

| Item | Cost |
|------|------|
| Polygon.io Advanced | $199/mo |
| Unusual Whales | $48/mo |
| Perplexity Sonar API | ~$50/mo |
| Hetzner CCX23 VPS | ~$45/mo |
| Anthropic API (Claude) | $100–300/mo |
| IBKR OPRA market data | $4.50/mo |
| IBKR commissions | ~$2.50/contract round trip |
| **Total (ex-commissions)** | **~$450–650/mo** |

> Commission cost depends on trade frequency. At 3 trades/week × 4 contracts/trade: ~$120/mo.

---

## Repository Structure

```
sentinel/
├── README.md
├── .gitignore
├── docs/
│   ├── setup-guide.md          # Complete from-scratch setup
│   ├── architecture.md         # Full system architecture
│   ├── phase-0-paper.md        # Paper trading setup and exit criteria
│   ├── phase-1-alerts.md       # Alerts-only operation guide
│   ├── phase-2-automated.md    # Automated execution (IBKR)
│   ├── api-reference.md        # All APIs: purpose, usage, cost
│   └── troubleshooting.md      # Common issues and fixes
├── openclaw/
│   ├── SOUL.md                 # Sentinel's identity and principles
│   ├── AGENTS.md               # Operating manual
│   ├── anchor.md               # Immutable rules (compaction-proof)
│   ├── MEMORY.md               # Long-term memory template
│   └── system/
│       └── context-buffer.md   # Cross-session state template
├── docker/
│   ├── docker-compose.yml      # Core stack (Phase 0/1)
│   ├── docker-compose.phase2.yml  # Adds IB Gateway
│   ├── .env.example            # All environment variables
│   └── prometheus.yml          # Prometheus scrape config
└── scripts/
    ├── check_vix.py
    ├── calculate_gex.py
    ├── check_calendar.py
    ├── polymarket_scan.py
    ├── uw_flow_scan.py
    ├── perplexity_scan.py
    ├── generate_signal.py
    ├── format_alert.py
    ├── paper_trade.py
    ├── daily_report.py
    ├── ibkr_place_ic.py        # Phase 2 only
    └── ibkr_close_all.py       # Phase 2 only
```

---

## Quick Start

See [docs/setup-guide.md](docs/setup-guide.md) for the complete setup walkthrough.

**Prerequisites:** A Hetzner VPS, Docker, and API keys for the four data services.

```bash
# Install OpenClaw
npm install -g openclaw
openclaw setup

# Clone this repo into your OpenClaw workspace
git clone https://github.com/yourhandle/sentinel.git ~/.openclaw/workspace/sentinel

# Configure environment
cp docker/.env.example docker/.env
# Edit docker/.env with your API keys

# Start the stack
cd docker
docker compose up -d
```

---

## Commands

| Command | Action |
|---------|--------|
| `/status` | Current circuit breaker states, open positions, today's P&L |
| `/paper` | Switch to paper trading mode |
| `/alerts` | Switch to alerts-only mode |
| `/live` | Enable live execution (requires confirmation) |
| `/save` | Write session memory, update context buffer |
| `/audit` | Spawn SRE, Security, and Trading Performance audit agents |
| `/kill` | Emergency halt: close all positions, set Redis kill switch |

---

## Disclaimer

This software is for educational and research purposes. Trading options involves substantial risk of loss. Past simulated performance does not guarantee future results. Nothing here constitutes financial advice. You are responsible for your own trading decisions.

---

## License

MIT
