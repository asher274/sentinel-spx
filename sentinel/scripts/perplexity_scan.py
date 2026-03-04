#!/usr/bin/env python3
"""
perplexity_scan.py — Pre-market news scan via Perplexity Sonar API.

Queries overnight SPX-relevant financial news and classifies macro risk level.
Run at ~9:00 AM ET before signal generation.

Output JSON to stdout. Logging to stderr.
"""

import json
import logging
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

# Load env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.trading"))

# Logging to stderr
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [perplexity_scan] %(levelname)s %(message)s",
)
log = logging.getLogger("perplexity_scan")

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# Risk keywords for classification
HIGH_RISK_KEYWORDS = [
    "crash", "circuit breaker", "halt", "emergency", "crisis",
    "collapse", "panic", "war", "attack", "default", "bankruptcy",
    "fed emergency", "black swan",
]
MEDIUM_RISK_KEYWORDS = [
    "recession", "selloff", "sell-off", "plunge", "tumble", "slump",
    "shock", "surge in volatility", "vix spike", "downgrade",
    "geopolitical", "tariff", "sanctions", "miss expectations",
    "disappointing", "weaker than expected",
]


def classify_risk_level(summary: str, headlines: list) -> str:
    """
    Classify risk level from summary + headlines text.

    Returns 'high', 'medium', or 'low'.
    """
    combined_text = (summary + " " + " ".join(headlines)).lower()

    for kw in HIGH_RISK_KEYWORDS:
        if kw in combined_text:
            log.warning(f"HIGH risk keyword detected: '{kw}'")
            return "high"

    for kw in MEDIUM_RISK_KEYWORDS:
        if kw in combined_text:
            log.info(f"MEDIUM risk keyword detected: '{kw}'")
            return "medium"

    return "low"


def extract_headlines(content: str) -> list:
    """
    Extract bullet-point headlines from Perplexity response content.
    Looks for lines starting with '-', '*', or numbered list items.
    Returns up to 10 headline strings.
    """
    headlines = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Bullet points
        if stripped.startswith(("- ", "* ", "\u2022 ")):
            headlines.append(stripped[2:].strip())
        # Numbered list items: "1. Headline text"
        elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in (".", ")"):
            headlines.append(stripped[2:].strip())
    return headlines[:10]


def query_perplexity() -> dict:
    """
    Query Perplexity Sonar API for overnight SPX-relevant news.
    Returns dict with 'summary', 'headlines', and raw 'content'.
    """
    if not PERPLEXITY_API_KEY:
        raise ValueError("PERPLEXITY_API_KEY not set")

    prompt = (
        "Provide a concise pre-market briefing for SPX options traders for today's US trading session. "
        "Focus on: overnight futures moves, key macro news, Fed/FOMC commentary, geopolitical risks, "
        "earnings that could move the market, and any VIX or volatility drivers. "
        "List the top 5-8 most important headlines as bullet points. "
        "Then provide a 2-3 sentence summary of the overall macro risk tone (bullish/bearish/neutral). "
        "Be factual and concise."
    )

    payload = {
        "model": "sonar",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a pre-market financial research assistant. "
                    "Provide accurate, concise, fact-based market summaries. "
                    "Do not give trading advice. Report what is known, not speculation."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "max_tokens": 600,
        "temperature": 0.2,
    }

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }

    log.info("Querying Perplexity Sonar API for pre-market news...")
    resp = requests.post(PERPLEXITY_API_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    log.info(f"Perplexity response received ({len(content)} chars)")

    headlines = extract_headlines(content)
    log.info(f"Extracted {len(headlines)} headlines")

    # Summary: non-bullet lines, up to 5
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    summary_lines = [
        ln for ln in lines
        if not ln.startswith(("-", "*", "\u2022"))
        and not (len(ln) > 1 and ln[0].isdigit() and ln[1] in (".", ")"))
    ]
    summary = " ".join(summary_lines[:5]).strip()
    if not summary:
        summary = content[:400].strip()

    return {
        "summary": summary,
        "headlines": headlines,
        "raw_content": content,
    }


def main():
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    try:
        scan_result = query_perplexity()
        summary = scan_result["summary"]
        headlines = scan_result["headlines"]

        risk_level = classify_risk_level(summary, headlines)
        log.info(f"Risk level classified: {risk_level}")

        result = {
            "summary": summary,
            "risk_level": risk_level,
            "headlines": headlines,
            "timestamp": timestamp,
        }
        print(json.dumps(result))

    except requests.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else "N/A"
        log.error(f"Perplexity API HTTP error: {e} — status {status_code}")
        result = {
            "summary": "Perplexity API unavailable",
            "risk_level": "medium",
            "headlines": [],
            "error": f"HTTP error: {e}",
            "timestamp": timestamp,
        }
        print(json.dumps(result))
        sys.exit(1)

    except requests.RequestException as e:
        log.error(f"Perplexity API request failed: {e}")
        result = {
            "summary": "Perplexity API unavailable",
            "risk_level": "medium",
            "headlines": [],
            "error": f"Request failed: {e}",
            "timestamp": timestamp,
        }
        print(json.dumps(result))
        sys.exit(1)

    except Exception as e:
        log.error(f"Unexpected error in perplexity_scan: {e}", exc_info=True)
        result = {
            "summary": "Scan failed",
            "risk_level": "high",
            "headlines": [],
            "error": str(e),
            "timestamp": timestamp,
        }
        print(json.dumps(result))
        sys.exit(1)


if __name__ == "__main__":
    main()
