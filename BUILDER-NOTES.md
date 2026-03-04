# Builder Notes — Read Before Finalizing

## Critical Context

These docs will be handed to a **brand new OpenClaw instance** (Sentinel) so it can **set itself up**. This changes the framing of almost every document.

## Document Audience Split

### README.md — Human Only
One document written for the human operator. Covers:
- What Sentinel is (brief)
- Prerequisites (accounts, API keys to gather)
- VPS/Docker setup steps (same VPS, new isolated Docker stack)
- How to install OpenClaw and point it at the openclaw/ directory
- How to hand off to Sentinel ("once running, Sentinel takes over from here")

That's it. Clean. Short. Human hands off to the AI.

### Everything Else — AI-Facing (Sentinel reads these)

All other documents are written AS IF Sentinel is reading them on first boot to understand itself and get operational. This means:

- **SOUL.md** — "You are Sentinel. This is who you are." (second person, direct address to the AI)
- **AGENTS.md** — Full operating manual. Must include a Session Startup Sequence: exact steps Sentinel runs every session (what files to read, in what order, what to check)
- **anchor.md** — Compaction-proof immutable rules. Written to survive context resets.
- **MEMORY.md** — Starter template. Pre-populated with key system facts (port numbers, DB credentials structure, strategy parameters) so Sentinel isn't starting completely blind
- **system/context-buffer.md** — Current state template. On first boot: phase = 0 (paper trading), all circuit breakers clear, no open positions
- **docs/architecture.md** — Deep reference. Sentinel reads this when it needs detail on strategy mechanics, circuit breaker thresholds, agent structure
- **docs/phase-0-paper.md** — Sentinel reads this to understand what it needs to do in Phase 0 and what the exit criteria are before it can recommend Phase 1
- **docs/phase-1-alerts.md** — What Sentinel does in Phase 1: how to format alerts, what to include, when to fire them
- **docs/phase-2-automated.md** — What Sentinel does in Phase 2: IBKR integration, order execution, Guardian activation

### Python Scripts
Scripts are tools Sentinel calls via exec. Each script's header comment should explain what it does, what args it accepts, and what JSON it returns — written for the AI reading the source to understand the tool.

## Tone for AI Documents

- Direct address ("You are Sentinel", "When you wake up each session, do this...")
- Imperative mood for procedures ("Read SOUL.md first. Then read anchor.md.")
- No passive voice in instructions
- Confidence levels and uncertainty flagged explicitly (this matches Sentinel's own personality)

## Session Startup Sequence (must be in AGENTS.md)

Every session, Sentinel must:
1. Read SOUL.md — who you are
2. Read anchor.md — immutable rules (these survive compaction)
3. Read system/context-buffer.md — what's in flight
4. Read memory/YYYY-MM-DD.md (today) — recent context
5. Read system/circuit-breaker-state.json — any active breakers?
6. Check cron job health
7. Check data feed connectivity (VIX, Polygon, Redis)
8. Brief the operator if anything notable. Otherwise greet and stand ready.

## Infrastructure Note
- Linux VPS (isolated Docker network)
- Isolated Docker network: `sentinel-net`
- All containers prefixed `sentinel-`
- docker-compose.yml uses `name: sentinel`
- Setup guide must include pre-flight port conflict check
- Ports to use: postgres 5433, redis 6380, grafana 3001 (avoids conflicts with existing stack)
- Separate OpenClaw config: `~/.sentinel/` directory

## Audit Pass Additions

Add a 4th audit pass — **AI Readability:**
- Read each AI-facing doc as if you are a fresh AI with no prior context. Is everything self-contained?
- Does AGENTS.md tell Sentinel exactly what to do on first boot?
- Does anchor.md cover all commands (/save, /audit, /kill, /status, /paper, /alerts, /live)?
- Would Sentinel know what phase it's in from context-buffer.md alone?
- Does MEMORY.md contain enough pre-populated facts that Sentinel isn't guessing about its own infrastructure?
