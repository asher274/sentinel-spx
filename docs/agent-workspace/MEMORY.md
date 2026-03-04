# MEMORY.md — Sentinel Long-Term Memory

_Load in main session only. Curated state, trends, lessons. Update with /save._

---

## System State

- **Current phase:** Phase 0 (Paper Trading) — not yet transitioned
- **Phase 0 progress:** 0 / 50 paper trades required
- **Phase 0 started:** not yet — begin on first qualifying trading day (Mon/Tue/Thu)

---

## Infrastructure

- **VPS:** Hetzner (shared with main OpenClaw instance, isolated Docker network)
- **Docker network:** sentinel-net
- **Ports:** postgres 5433 | redis 6380 | grafana 3001 | prometheus 9091
- **Backup:** nightly-backup cron, 2:00 AM ET daily

---

## Strategy

- **Instrument:** SPX 0DTE iron condors
- **Trading days:** Monday, Tuesday, Thursday only
- **Entry window:** 10:15–10:30 AM ET
- **Target:** 50% of initial credit received
- **Stop:** 2x credit received (or defined max loss at entry)
- **Force close:** 3:45 PM ET hard, 3:50 PM absolute

---

## APIs & Data Sources

- **Polygon.io** — GEX, VIX, options chain data
- **Unusual Whales** — institutional flow scanning
- **Polymarket** — event probabilities (free tier)
- **Perplexity Sonar** — pre-market research and headline scanning

---

## Circuit Breakers

- **Status:** All clear on initial deploy
- **Last triggered:** never
- **Last reset:** n/a

---

## Performance

_Populate as trades accumulate._

- Win rate: — (0 trades)
- Average credit collected: —
- Average P&L per trade: —
- Best trade: —
- Worst trade: —
- Consecutive win streak: —
- Consecutive loss streak: —

---

## Key Preferences

- Brief and direct. Report in numbers.
- No hedging when a call can be made.
- One notification per event. No fan-out.
- Decisions over summaries. Numbers over adjectives.

---

## Lessons Learned

_Append as you learn. Never delete._

(Empty — populate as trades and events accumulate.)

---

## Open Items

- Complete Phase 0: 50+ paper trades over 30+ calendar days
- Verify all circuit breaker triggers function correctly before Phase 1 transition
- Confirm IBKR paper account connectivity before first paper trade
