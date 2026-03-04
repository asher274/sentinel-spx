# Sentinel — Phase 1: Alerts Only

> **Status:** NOT YET ACTIVE  
> **Phase:** 1 of 3  
> **Prerequisites:** Phase 0 exit criteria met + Asher approval  
> **Goal:** Real-money signal validation via human execution, before automation.

---

## What Is Phase 1?

Phase 1 is alert-only mode. Sentinel identifies iron condor setups with the same rigor as Phase 0, but instead of logging paper trades internally, it **posts rich trade alerts to Discord `#signals`** for Asher to execute manually.

Phase 1 bridges the gap between simulation and automation. The signal logic is tested against real market fills, real slippage, and real execution friction. The system learns whether its setups are executable — not just theoretically profitable.

During Phase 1:
- Sentinel posts every GO signal to `#signals` with full setup details
- Asher decides whether to execute each alert
- Asher logs actual fills to `paper_trades.json` using `paper_trade.py`
- The system tracks theoretical P&L (what would have happened at signal time)
- Theoretical vs. actual P&L delta is measured to quantify execution slippage

---

## What Phase 1 Is NOT

- It does **not** place orders automatically. Any order is placed by Asher manually in the IBKR desktop or mobile app.
- It does **not** guarantee that Asher must trade every alert. Asher may skip alerts for any reason.
- It does **not** replace Phase 0. Phase 1 only begins after Phase 0 criteria are fully met.

---

## How to Format and Post Signals to #signals

### Automatic Path (Recommended)

The full pipeline runs automatically via OpenClaw scheduling:

```bash
python scripts/generate_signal.py | python scripts/format_alert.py
```

The agent posts the resulting `alert_text` to Discord `#signals` using the configured bot token.

### Manual Path (Testing or Fallback)

```bash
# Step 1: Generate signal
python scripts/generate_signal.py > /tmp/signal.json

# Step 2: Format alert
cat /tmp/signal.json | python scripts/format_alert.py > /tmp/alert.json

# Step 3: Review alert
cat /tmp/alert.json | jq -r '.alert_text'

# Step 4: Post manually to Discord (copy/paste alert_text)
```

### Sample Alert (Discord Output)

```
🟢 SENTINEL — IRON CONDOR SIGNAL 🟢
━━━━━━━━━━━━━━━━━━━━━━━━

SETUP: SPX 0DTE Iron Condor
```
CALL SPREAD:  5820 / 5845
PUT SPREAD:   5670 / 5695
WING WIDTH:   25pt
```

🎯 Credit Target: $1.50–$2.50
🛡 Stop (per side): $1.50/side
🎯 Profit Target: 50% close (~$0.75)
⏰ Force Close: 3:45 PM ET

CONDITIONS
📈 VIX: `18.4` — regime `normal`
📈 GEX Walls: put `5695` / call `5820`

FILTER RESULTS
  ✅ `DAY_OF_WEEK`
  ✅ `TIME_WINDOW`
  ✅ `VIX` VIX 18.4 (normal)
  ✅ `CALENDAR`
  ✅ `GEX` walls 5695/5820
  ✅ `POLYMARKET` macro=low

CONFIDENCE: 🟢 HIGH (100%)

_All filters passed_
_Signal time: 2026-03-04T10:12:33 UTC_
```

---

## Tracking Theoretical P&L

Sentinel tracks two P&L streams in Phase 1:

### 1. Theoretical P&L (Automated)

The system logs the signal's setup at the time of the GO decision. At market close, it calculates what the P&L would have been if executed at the target credit mid.

This is logged automatically by `paper_trade.py --entry` when called immediately after signal generation (even if Asher doesn't execute). Use `--notes "theoretical_only"` to mark these.

```bash
# Log theoretical entry immediately after signal
cat /tmp/signal.json | python scripts/paper_trade.py --entry --notes "theoretical_only"

# At 3:45 PM ET — log theoretical exit
python scripts/paper_trade.py --exit --id PT-XXXX --exit-credit 0.00 --reason force_close --notes "theoretical_only"
```

### 2. Actual P&L (Manual)

When Asher executes an alert:

```bash
# Log actual fill (Asher enters the credit received from IBKR)
python scripts/paper_trade.py --entry --credit-received 1.78 --notes "actual_fill"

# Log actual exit
python scripts/paper_trade.py --exit --id PT-XXXX --exit-credit 0.91 --reason profit_target --notes "actual_fill"
```

### Slippage Analysis

The daily report and weekly review should compare:
- `theoretical_pnl` (what the system expected)
- `actual_pnl` (what Asher received)

If theoretical P&L is consistently positive but actual P&L is significantly worse, the setup parameters need adjustment (e.g., widen credit targets to account for slippage, adjust stop levels).

---

## Measuring Asher Execution Confirmation Rate

The **execution confirmation rate** measures how often Asher actually trades an alert vs. receives it.

This matters because in Phase 2, the bot will trade every GO signal. If Asher is only trading 50% of them due to personal judgment, Phase 2 will be running signals that Asher would have skipped.

### How to Track

For every GO signal in Discord #signals, Asher responds with one of:
- ✅ — Executed (logs the fill)
- ⏭ — Skipped (posts reason in thread)
- ❌ — Signal was wrong/rejected (posts reason)

The bot (or Asher manually) tracks the ratio:

```
Execution Rate = (trades executed) / (GO signals posted)
```

### Target Confirmation Rate

- **Phase 1 Target:** ≥ 80% execution rate over 20+ alert cycles
- Below 80%: Review why Asher is skipping signals. Are the alerts arriving too late? Is setup quality inconsistent?
- Above 80%: System is reliable enough to consider automation

---

## Phase 1 Alert Schedule

Phase 1 runs the same schedule as Phase 0:

| Time (ET) | Action |
|-----------|--------|
| 8:55 AM | Pre-market scan (auto) |
| 10:05 AM | Signal generation starts |
| 10:05–10:35 AM | Signal window — GO or NO_TRADE posted to #signals |
| 3:45 PM | Force close reminder posted to #alerts |
| 4:00 PM | Daily report to #daily-report |

### Response Time Requirement

Asher must be able to execute within **5 minutes** of a GO alert posting. The entry window closes at 10:35 AM ET. Alerts arriving after 10:30 AM may not be executable.

If Asher consistently misses the window due to timing, the scheduling parameters in `generate_signal.py` (`ENTRY_WINDOW_START`/`END`) should be adjusted.

---

## NO_TRADE Alerts

Every NO_TRADE is also posted to `#signals` (or `#alerts`) so Asher can review filter failures. This is valuable data — it shows which conditions are blocking trade frequency.

A healthy day looks like:
- 1 GO signal → 1 trade executed
- Or 1 NO_TRADE with a clear reason (calendar event, VIX, GEX negative)

A problematic pattern:
- Consistently NO_TRADE due to GEX negative → investigate GEX regime frequency
- Consistently NO_TRADE due to time window → check scheduling
- GO signal with low confidence (<75%) → review which filter is degraded

---

## Phase 1 Transition Criteria

All of the following must be met before advancing to Phase 2:

### Criterion 1: Phase 0 Criteria Fully Met
All Phase 0 exit criteria confirmed and documented. (See `docs/phase-0-paper.md`.)

### Criterion 2: ≥ 20 Alert Cycles
At least 20 GO signals have been posted and responded to (executed or explicitly skipped with reason).

### Criterion 3: ≥ 80% Execution Confirmation Rate
Over the 20+ alert cycles, Asher has executed ≥ 80% of signals within the entry window.

### Criterion 4: Actual P&L Positive
Cumulative actual P&L (from Asher's real fills, not theoretical) is positive. Breakeven is acceptable with improving trend.

### Criterion 5: Slippage Within Tolerance
Theoretical P&L minus actual P&L (slippage) is < $0.50 per spread on average. If slippage is larger, adjust credit targets or entry timing before proceeding.

### Criterion 6: Infrastructure Ready for Phase 2
- IB Gateway container deployed and tested (paper mode)
- `ibkr_place_ic.py` tested end-to-end against IBKR paper account
- Redis circuit breakers confirmed functional
- Drawdown tracking implemented

### Criterion 7: Asher Explicit Approval
Asher reviews all Phase 1 data and explicitly types in Discord:  
`"Approved: Sentinel Phase 1 complete. Advance to Phase 2."`

`SENTINEL_PHASE=2` is then set manually in `.env.trading`.

---

## Common Questions

**Q: Should I execute every single GO signal in Phase 1?**  
A: Yes, whenever possible. The goal of Phase 1 is to measure execution confirmation. If you skip signals, log the reason in the Discord thread. High skip rates need to be understood before automation.

**Q: What if I execute a trade but the credit is way below target?**  
A: Log the actual credit received. This is critical data. If you consistently can't hit the credit target, the setup parameters need adjustment before Phase 2.

**Q: Can I modify the setup (different strikes, different credit) and still log it?**  
A: Log any modification clearly in `--notes`. The comparison between signal strikes and executed strikes helps calibrate Phase 2 order parameters.

**Q: What if the GO signal is clearly wrong (e.g., breaking news after signal time)?**  
A: Skip the trade, post ❌ in the Discord thread with explanation. This is a legitimate skip. Track it, but don't count it against execution rate if the skip is justified by post-signal information.

---

*See `docs/phase-2-automated.md` for what comes next.*
