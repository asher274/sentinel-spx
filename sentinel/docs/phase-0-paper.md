# Sentinel — Phase 0: Paper Trading

> **Status:** ACTIVE  
> **Phase:** 0 of 3  
> **Goal:** Validate signal quality and system reliability before risking real capital.

---

## What Is Phase 0?

Phase 0 is a fully autonomous paper trading simulation. The system operates exactly as it would in live trading — running all signal filters, generating setups, and logging trades — but **no real money is ever placed**.

Paper trading exists to answer one question: **Is Sentinel's signal logic sound enough to risk real capital?**

It takes at least 30 days and 50 trades to answer that question with confidence. During this time, every GO signal, every filter fail, every forced close, and every P&L result is logged and reviewed. Only when the data clearly supports progression — and the operator explicitly approves — does Sentinel advance to Phase 1.

There are no shortcuts. The only path forward is through Phase 0.

---

## What Phase 0 Is NOT

- It is **not** a test of whether the system is "working." It is a disciplined evaluation of whether the *strategy* has edge.
- It is **not** a guarantee that live trading will be profitable. Past paper performance does not guarantee future results.
- It is **not** optional. Skipping Phase 0 is how people blow up accounts.

---

## Scripts to Run and When

### Daily Schedule

| Time (ET) | Action | Command |
|-----------|--------|---------|
| **8:55 AM** | Pre-market news scan | `python scripts/perplexity_scan.py` |
| **8:57 AM** | Options flow scan | `python scripts/uw_flow_scan.py` |
| **9:00 AM** | Agent session starts, reads pre-market | _(OpenClaw auto-start)_ |
| **10:05 AM** | Run signal generation | `python scripts/generate_signal.py` |
| **10:05–10:35 AM** | Signal window active | _(one GO signal max per day)_ |
| **10:35 AM** | Entry window closes | _(NO_TRADE if no GO)_ |
| **~10:05–10:15 AM** | If GO: log paper entry | `python scripts/paper_trade.py --entry` |
| **3:45 PM** | Force-close any open paper trades | `python scripts/paper_trade.py --exit --reason force_close` |
| **4:00 PM** | Generate daily report | `python scripts/daily_report.py` |
| **4:05 PM** | Post report to Discord | _(agent posts `report_text`)_ |

### Manual Run (Testing)

To test the full pipeline manually:

```bash
cd /path/to/sentinel

# Step 1: Pre-market context
python scripts/perplexity_scan.py
python scripts/uw_flow_scan.py

# Step 2: Signal generation (outputs GO or NO_TRADE)
python scripts/generate_signal.py

# Step 3: Format as Discord alert (pipe from signal)
python scripts/generate_signal.py | python scripts/format_alert.py

# Step 4: Log a paper entry (if GO)
python scripts/paper_trade.py --entry --credit-received 1.75

# Step 5: Log a paper exit
python scripts/paper_trade.py --exit --id PT-ABC123 --exit-credit 0.85 --reason profit_target

# Step 6: Generate daily report
python scripts/daily_report.py
```

---

## Logging to trade-journal.md

In addition to the automated `paper_trades.json` log, maintain a human-readable **trade journal** at `trade-journal.md` in the project root.

The journal captures qualitative context that automated logs miss: what the market was doing, why a filter failed or passed, what was unusual about the day.

### Journal Entry Format

Each trading day gets one entry:

```markdown
## 2026-03-04 (Tuesday)

**Signal Time:** 10:12 AM ET  
**Decision:** GO  
**Setup:** SPX IC 5720/5695 | 5820/5845 | wing=25pt  
**Credit Target:** $1.50–$2.50  
**Confidence:** 92%  

**Filter Results:**
- VIX: 18.4 (normal) ✅
- Calendar: No events ✅
- GEX: Positive (+$2.1B) | put wall 5695 | call wall 5820 ✅
- Polymarket: low risk ✅

**Entry:** 10:15 AM ET | credit received: $1.82 | Trade ID: PT-F3A1B2

**Exit:** 1:48 PM ET | exit credit: $0.91 | reason: profit_target | P&L: +$0.91

**Notes:**
VIX opened lower than yesterday. GEX regime flipped positive right after open.
Flow was neutral — no large UW prints on SPX. Clean setup day.

**Perplexity Summary:** Markets calm overnight. No macro catalysts. Fed speakers off calendar.
```

### When to Write

Write the journal entry:
1. **After the signal** — fill in decision, filters, setup
2. **After entry** — add trade ID and credit received
3. **After exit** — add exit time, credit, P&L, reason
4. **End of day** — add qualitative notes

The journal is the operator's primary review tool during Phase 0 evaluations. Keep it honest. Note anomalies, errors, close calls, and anything unusual.

---

## paper_trades.json

`paper_trades.json` is the source of truth for automated stats. It lives in the project root and is managed by `paper_trade.py`.

### File Structure

```json
{
  "PT-F3A1B2": {
    "trade_id": "PT-F3A1B2",
    "status": "closed",
    "entry_time": "2026-03-04T10:15:00",
    "exit_time": "2026-03-04T13:48:00",
    "short_call": 5820,
    "long_call": 5845,
    "short_put": 5695,
    "long_put": 5670,
    "wing_width": 25,
    "credit_target_low": 1.5,
    "credit_target_high": 2.5,
    "stop_per_side": 1.5,
    "profit_target_pct": 50,
    "credit_received": 1.82,
    "exit_credit": 0.91,
    "pnl": 0.91,
    "exit_reason": "profit_target",
    "notes": null
  }
}
```

### Exit Reasons

| Reason | Meaning |
|--------|---------|
| `profit_target` | 50% credit captured |
| `stop_loss` | Per-side loss exceeded total IC credit |
| `force_close` | Manually closed at 3:45 PM ET |
| `manual` | Human-initiated close |

### Do NOT Edit Manually

Do not manually edit `paper_trades.json` to change P&L or outcomes. The audit trail must be clean. If a correction is needed, add a note and log it in the trade journal. Manipulated paper results are worthless.

---

## Daily Report

`daily_report.py` generates the end-of-day performance summary. It:

1. Reads all trades in `paper_trades.json` for today
2. Computes daily P&L, win/loss counts, win rate
3. Reads `openclaw/MEMORY.md` for any session notes
4. Builds a formatted Discord message

The report is posted to Discord `#daily-report` channel at 4:00 PM ET.

**Sample report output (Discord):**
```
📊 SENTINEL DAILY REPORT
📅 Tuesday, March 04, 2026
────────────────────────────

Day Type: trading_day (Tuesday)

TODAY'S ACTIVITY
• Signals generated: 1
• Trades entered: 1
• Trades closed: 1
• Trades still open: 0

TODAY'S P&L
🟢 Daily P&L: +$0.91
• Wins: 1 | Losses: 0
• Win rate today: 100.0%

CUMULATIVE (Phase 0)
• Total trades: 12 closed / 0 open
• Cumulative P&L: +$8.43
• Win rate all-time: 66.7% (8W / 4L)

PHASE 0 PROGRESS
• Trade count: 12/50 (24%)
• Win rate: 66.7% (target: 55–65%) ✅

_Report generated: 2026-03-04T21:00:05 UTC_
```

---

## Phase 0 Exit Criteria

All of the following must be satisfied before Sentinel can advance to Phase 1. There are no exceptions.

### Criterion 1: Trade Volume ≥ 50

**Minimum 50 paper trades must be logged** in `paper_trades.json` with valid entry and exit records.

- A trade counts only if it has: `entry_time`, `exit_time`, `credit_received`, `exit_credit`, `pnl`, and `exit_reason`
- Trades cancelled due to circuit breakers do not count
- Each trading day (Mon/Tue/Thu) can contribute at most 1 trade

**Check:** `python scripts/daily_report.py | jq '.total_trades_all_time'`

---

### Criterion 2: Duration ≥ 30 Calendar Days

**The system must have been running for at least 30 consecutive calendar days** since Phase 0 was activated.

This ensures the system has been tested across varying market conditions — including high-VIX days, FOMC weeks, earnings seasons, and quiet periods.

**Check:** Review `openclaw/MEMORY.md` for Phase 0 start date.

---

### Criterion 3: Win Rate 55–65% (Sustained)

**The cumulative win rate across all Phase 0 trades must be between 55% and 65%**, evaluated at the 50-trade mark.

- Win rate below 55%: signals are underperforming. Do not advance.
- Win rate above 65%: investigate whether signals are over-fitted to current conditions. Advance cautiously with the operator review.
- Win rate 55–65%: healthy range that supports positive expectancy with 1:1 reward/risk.

**Check:** `python scripts/daily_report.py | jq '.cumulative_win_rate'`

**Note:** Win rate is evaluated on *closed* trades only. Do not advance based on open trades.

---

### Criterion 4: Zero System Errors for 5 Consecutive Trading Days

**No script failures, API errors, or unhandled exceptions for 5 consecutive trading days** immediately before the advancement review.

"System error" means:
- A script exited with code 1 (except for expected NO_TRADE outcomes)
- An API returned an HTTP error that prevented signal generation
- A paper trade failed to log due to a code error
- `generate_signal.py` produced no output on a trading day

**Check:** Review `#sentinel-health` Discord channel and stderr logs for the last 5 trading days.

---

### Criterion 5: Daily Reports for 10+ Trading Days

**Daily reports must have been generated and posted for at least 10 trading days** during Phase 0.

This demonstrates the reporting infrastructure is reliable enough for Phase 1.

**Check:** Count entries in Discord `#daily-report` channel.

---

### Criterion 6: the operator Explicit Approval

**the operator must explicitly review the Phase 0 results and give a go/no-go decision** before the system can advance.

The review includes:
1. Reading all 10+ daily reports
2. Reviewing `trade-journal.md` for qualitative analysis
3. Verifying `paper_trades.json` is not manipulated
4. Confirming all 5 criteria above are met
5. Typing explicit confirmation in Discord: `"Approved: Sentinel Phase 0 complete. Advance to Phase 1."`

**There is no automated advancement.** `SENTINEL_PHASE` in `.env.trading` is only changed by the operator manually.

---

## What To Do If A Criterion Is Not Met

| Scenario | Action |
|----------|--------|
| Win rate < 55% at 50 trades | Do NOT advance. Review filter logic. Paper trade another 20–30 trades. |
| Win rate > 65% | Flag for the operator review. May advance but watch for over-fitting. |
| System error streak | Fix the root cause first. Reset the 5-day error clock. |
| Fewer than 50 trades in 30 days | Continue. Check that the day-of-week filter is working correctly. |
| Reports not posting | Fix Discord integration. Reports are a hard requirement. |

---

## Common Questions

**Q: Can I backfill paper trades from before Phase 0 was formally started?**  
A: No. Only trades logged via `paper_trade.py` after the official Phase 0 start date count. Retroactive entries invalidate the evaluation.

**Q: What if the market is closed (holiday)?**  
A: Market holidays are acceptable gaps. They do not reset the 5-day error clock unless there was an actual error.

**Q: Should I run the system on Wednesday and Friday even though we don't trade?**  
A: Yes. Run the pre-market scan and signal generation daily. The day-of-week filter will issue NO_TRADE. This tests the system's non-trading-day behavior and keeps the process rhythm consistent.

**Q: What happens to open paper trades at end of day?**  
A: `paper_trade.py --exit --reason force_close` must be run at 3:45 PM ET for any open trades. The force close P&L is calculated from the credit received vs. current mark (use $0 exit credit if expiring worthless, otherwise use actual mark).

---

*See `docs/phase-1-alerts.md` for what comes next.*
