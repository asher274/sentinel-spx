# Sentinel — Phase 2: Automated Execution

> **⚠️ NOT YET ACTIVE ⚠️**  
> **Phase:** 2 of 3  
> **Prerequisites:** Phase 0 AND Phase 1 fully complete + Asher explicit approval  
> **Status:** DESIGN REFERENCE ONLY — DO NOT IMPLEMENT WITHOUT EXPLICIT APPROVAL

---

## ⛔ Important Notice

**Phase 2 is not active. This document is a forward-looking design reference.**

No automated order placement is implemented or should be implemented until:

1. Phase 0 exit criteria are fully met (see `docs/phase-0-paper.md`)
2. Phase 1 exit criteria are fully met (see `docs/phase-1-alerts.md`)
3. Asher explicitly types approval in Discord
4. `SENTINEL_PHASE=2` is manually set in `.env.trading`
5. All Phase 2 infrastructure is tested in IBKR paper mode
6. A final pre-launch checklist (documented below) is completed

Automated trading without completing these steps will result in uncontrolled risk. **Do not rush this.**

---

## What Phase 2 Does

Phase 2 integrates live order execution via Interactive Brokers (IBKR). The bot:

1. Generates GO signals using the same pipeline as Phases 0 and 1
2. Posts the alert to Discord `#signals` (Phase 1 alerts continue as a transparency layer)
3. **Automatically places the iron condor order** via IBKR API
4. Monitors the position for profit target (50%) and stop-loss
5. Force-closes any open position at 3:45 PM ET
6. Logs all activity to `paper_trades.json` and Discord

The Phase 1 transparency layer (posting alerts to #signals before execution) is never removed. Every automated order is announced in Discord before it is placed.

---

## IBKR Integration

### 2.1 IB Gateway

Phase 2 uses the IBKR headless IB Gateway (not TWS). It runs in a Docker container:

```yaml
# docker/docker-compose.phase2.yml (fragment)
services:
  ib-gateway:
    image: ghcr.io/gnzsnz/ib-gateway:latest
    container_name: sentinel-ib-gateway
    environment:
      TWS_USERID: ${IBKR_USERNAME}
      TWS_PASSWORD: ${IBKR_PASSWORD}
      TRADING_MODE: ${IBKR_TRADING_MODE}   # paper or live
      VNC_SERVER_PASSWORD: ${VNC_PASSWORD}
    ports:
      - "127.0.0.1:4002:4002"   # API port (paper)
      - "127.0.0.1:5900:5900"   # VNC for debugging
    networks:
      - sentinel-net
    restart: unless-stopped
```

IB Gateway connects to IBKR servers and exposes a local socket API on port 4002 (paper) or 4001 (live).

### 2.2 ib_insync Library

The Python client library is `ib_insync`, which wraps the IBKR TWS API.

```bash
pip install ib_insync
```

Key objects used:

| Object | Purpose |
|--------|---------|
| `IB` | Main connection object |
| `Contract` | SPX option contract definition |
| `ComboLeg` | Iron condor leg definition |
| `Order` | Order type (LMT, MKT, etc.) |
| `Trade` | Submitted order status |

### 2.3 Connection Pattern

```python
from ib_insync import IB, Stock, Option, ComboLeg, Contract, Order

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=1, timeout=10)

# Always disconnect cleanly
try:
    # ... place orders ...
    pass
finally:
    ib.disconnect()
```

---

## ibkr_place_ic.py (Phase 2 Script — NOT YET ACTIVE)

`scripts/ibkr_place_ic.py` places a 4-leg iron condor order on SPX.

### Design Specification

**Input:** JSON from `generate_signal.py` (via stdin or file)  
**Output:** JSON with order ID, status, fill price

**Execution flow:**

```
1. Read GO signal (setup block)
2. Check all circuit breakers (Redis)
3. Check kill switch (Redis)
4. Resolve SPX option contracts via IBKR (today's expiry, OCC format)
5. Validate mid price is within credit target range
6. Build 4-leg ComboLeg order
7. Submit LMT order at credit mid
8. Wait up to 60s for fill
9. If not filled: adjust limit down by $0.05 increments (max 3 adjustments)
10. Log fill to paper_trades.json
11. Post to Discord #signals and #paper-trades
12. Exit 0 on fill, exit 1 on failure
```

**Order validation (pre-submission):**

- Verify IB Gateway is connected
- Verify account has sufficient buying power (margin check)
- Verify SPX is trading (market hours check)
- Verify strikes are valid (match resolved contracts)
- Verify credit mid is within `[credit_target_low - 0.25, credit_target_high + 0.25]`

If any validation fails: log error, post to #alerts, exit 1 (no order submitted).

### Order Type

Phase 2 uses **limit orders** on the combo contract (not individual legs). This reduces slippage risk vs. legging in.

```python
order = Order()
order.action = "SELL"
order.orderType = "LMT"
order.totalQuantity = contract_size  # starts at 1 contract per side (quarter size)
order.lmtPrice = round(credit_target_mid, 2)
order.transmit = True
```

### Position Sizing

Phase 2 uses a graduated size ramp:

| Stage | Size | Trigger |
|-------|------|---------|
| Phase 2 Start | Quarter size (1 contract) | SENTINEL_PHASE=2 set |
| Scale-up 1 | Half size (2 contracts) | After 10 profitable Phase 2 trades |
| Scale-up 2 | Full size (4 contracts) | After 20 profitable Phase 2 trades |

Size is stored in Redis key `sentinel:position_size` and updated manually by Asher after each scale-up milestone.

---

## ibkr_close_all.py (Phase 2 Script — NOT YET ACTIVE)

`scripts/ibkr_close_all.py` is the emergency position closer. It:

1. Queries all open SPX positions from IBKR
2. For each open iron condor leg: submits a market order to close
3. Waits up to 30 seconds for each fill
4. Posts confirmation of each close to Discord #alerts
5. If any close fails after 3 retries: pages Asher via Telegram
6. Exits 0 only when all positions are confirmed closed

This script is invoked by:
- The `/kill` Discord command
- Circuit breaker drawdown trigger (35% drawdown)
- End-of-day force close at 3:45 PM ET

**This script must be tested against IBKR paper account before Phase 2 goes live.**

---

## Theta/Guardian Roles

In the final Phase 2 architecture, the agent stack includes two specialized sub-agents:

### Theta Agent

**Role:** Position manager. Monitors open iron condor positions in real time.

**Responsibilities:**
- Poll open position P&L every 60 seconds during market hours
- Trigger profit-target close when position reaches 50% of credit
- Trigger stop-loss close when per-side loss reaches total IC credit
- Force-close at 3:45 PM ET regardless of P&L
- Post position updates to Discord #alerts on significant moves (>25% of max profit)

**Implementation:** OpenClaw sub-agent spawned after each order fill. Monitors IBKR position via `ib_insync`. Terminates after position is closed.

### Guardian Agent

**Role:** Risk monitor. Watches circuit breakers and account-level risk.

**Responsibilities:**
- Monitor daily P&L vs. circuit breaker thresholds
- Monitor VIX in real time during market hours
- Trigger circuit breakers when thresholds are crossed
- Activate kill switch on drawdown trigger
- Post all risk events to Discord #alerts

**Implementation:** Long-running OpenClaw sub-agent. Checks Redis circuit breaker keys on each signal generation call. Runs independently of Theta Agent.

---

## Order Validation Rules

Every order submission must pass this checklist before `ib.placeOrder()` is called:

| Check | Condition | Fail Action |
|-------|-----------|-------------|
| Kill switch | `cb:kill_switch == 0` | Abort, post to #alerts |
| All trading halt | `cb:all_trading:halted == 0` | Abort, post to #alerts |
| Strategy Alpha halt | `cb:strategy_alpha:halted == 0` | Abort, post to #alerts |
| Market hours | 9:30 AM–3:45 PM ET | Abort silently |
| Entry window | 10:05 AM–10:35 AM ET | Abort silently |
| IB Gateway connected | `ib.isConnected()` | Abort, post error to #health |
| Account margin | Buying power > position margin | Abort, post to #alerts |
| Strike validation | All 4 strikes resolve to valid contracts | Abort, post error |
| Credit validation | Mid price in `[low - 0.25, high + 0.25]` | Abort, retry signal |
| Duplicate check | No open positions for same expiry | Abort, post warning |

---

## Emergency Close Protocol

If the kill switch is activated while a position is open:

**Step 1:** `ibkr_close_all.py` runs immediately  
**Step 2:** MKT orders submitted for all open legs  
**Step 3:** Wait 30s per leg for fill confirmation  
**Step 4:** If fill not confirmed: retry with MKT order, 3 attempts  
**Step 5:** If all retries fail: send Telegram alert to Asher immediately  
**Step 6:** Log all actions to MEMORY.md  
**Step 7:** Post full status to Discord #alerts  

**Asher must manually verify all positions are closed in IBKR desktop before resuming.**

---

## Pre-Launch Checklist

Before activating `SENTINEL_PHASE=2`, complete all of the following:

### Infrastructure
- [ ] IB Gateway container running and stable for 48+ hours
- [ ] `ibkr_place_ic.py` tested against IBKR paper account (at least 5 test orders)
- [ ] `ibkr_close_all.py` tested against IBKR paper account (close all positions)
- [ ] Redis circuit breakers confirmed functional (test each trigger manually)
- [ ] Kill switch confirmed functional (activate → all orders blocked)
- [ ] Theta Agent sub-agent tested (position monitoring for simulated open trade)
- [ ] Guardian Agent sub-agent tested (circuit breaker monitoring)

### Data & Monitoring
- [ ] Grafana dashboard live and showing Phase 2 metrics
- [ ] Prometheus metrics confirmed scraping
- [ ] Discord alerts confirmed for all circuit breaker events
- [ ] Telegram failover confirmed (Asher receives test notification)

### Risk Controls
- [ ] Account size defined (`sentinel:account_size` in Redis)
- [ ] Daily loss threshold set (`3% × account_size`)
- [ ] Position size set to quarter size (`sentinel:position_size = 1`)
- [ ] Kill switch confirmed at `0` (inactive)

### Final Approval
- [ ] Asher reviews complete pre-launch checklist
- [ ] Asher confirms IBKR account funded and ready
- [ ] `IBKR_TRADING_MODE=paper` set for first Phase 2 week (paper mode with real signal timing)
- [ ] Asher explicitly types approval:  
  `"Approved: Sentinel Phase 2 launch. Live execution enabled."`
- [ ] `SENTINEL_PHASE=2` set in `.env.trading`
- [ ] OpenClaw gateway restarted to pick up new phase

---

## Phase 2 Milestones

| Milestone | Trigger | Action |
|-----------|---------|--------|
| Launch | Asher approval + SENTINEL_PHASE=2 | Paper mode execution begins |
| Live flip | Asher approval after 5 paper Phase 2 trades | Switch IBKR_TRADING_MODE=live |
| Scale-up 1 | 10 profitable live trades | sentinel:position_size = 2 (Asher sets) |
| Scale-up 2 | 20 profitable live trades | sentinel:position_size = 4 (Asher sets) |
| Monthly review | End of each month | Asher reviews drawdown, win rate, circuit breaker history |

---

## Operating Costs at Full Phase 2

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

At full size (4 contracts), commissions are ~$10/trade (4 contracts × 4 legs × ~$0.65/contract).  
At 3 trades/week: ~$120/mo in commissions.

---

*This document describes future functionality. Nothing here is currently active. See `docs/phase-0-paper.md` for current operating instructions.*
