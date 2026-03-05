#!/usr/bin/env python3
"""Post top-scored signals to Discord via webhook.

Usage:
    python discord_poster.py              # Post top signals
    python discord_poster.py --dry-run    # Preview without posting
    python discord_poster.py --top 5      # Post top 5 (default: 10)

Requires DISCORD_WEBHOOK_PULSE env var to be set.
"""

import argparse
import json
import logging
import os
import time
from pathlib import Path

import requests

from config import DATA_DIR

logger = logging.getLogger(__name__)

POSTED_FILE = DATA_DIR / "discord_posted.json"
SCORED_FILE = DATA_DIR / "scored.json"

# Content type -> embed color
TYPE_COLORS = {
    "paper": 0x3498DB,
    "repo": 0x2ECC71,
    "launch": 0xE74C3C,
    "article": 0x9B59B6,
    "discussion": 0xE67E22,
}
DEFAULT_COLOR = 0x95A5A6


def load_posted() -> set[str]:
    """Load the set of already-posted source_ids."""
    if POSTED_FILE.exists():
        try:
            data = json.loads(POSTED_FILE.read_text(encoding="utf-8"))
            return set(data)
        except (json.JSONDecodeError, TypeError):
            return set()
    return set()


def save_posted(posted: set[str]) -> None:
    """Persist the set of posted source_ids."""
    POSTED_FILE.write_text(
        json.dumps(sorted(posted), indent=2),
        encoding="utf-8",
    )


def load_scored() -> list[dict]:
    """Load scored items from data/scored.json."""
    if not SCORED_FILE.exists():
        logger.warning("Scored file not found: %s", SCORED_FILE)
        return []
    return json.loads(SCORED_FILE.read_text(encoding="utf-8"))


def build_embed(scored: dict) -> dict:
    """Build a Discord embed dict from a scored item."""
    item = scored.get("item", {})
    content_type = item.get("content_type", "article")
    color = TYPE_COLORS.get(content_type, DEFAULT_COLOR)
    score = scored.get("score", 0)
    tags = scored.get("tags", [])
    fit = scored.get("fit", {})

    # Score bar visualization
    filled = round(score)
    score_bar = "\u2588" * filled + "\u2591" * (10 - filled)

    fields = [
        {"name": "Score", "value": f"`{score_bar}` **{score:.1f}**/10", "inline": False},
    ]

    if tags:
        fields.append({"name": "Tags", "value": ", ".join(tags[:5]), "inline": True})

    fields.append({"name": "Type", "value": content_type.title(), "inline": True})
    fields.append({"name": "Source", "value": item.get("source", "unknown"), "inline": True})

    # Why unique from fit evaluation
    why_unique = fit.get("why_unique", "")
    if why_unique and "unavailable" not in why_unique.lower():
        if len(why_unique) > 200:
            why_unique = why_unique[:197] + "..."
        fields.append({"name": "Why it stands out", "value": why_unique, "inline": False})

    desc = item.get("description") or ""
    if len(desc) > 200:
        desc = desc[:197] + "..."

    embed = {
        "title": item.get("title", "Untitled"),
        "url": item.get("url"),
        "description": desc,
        "color": color,
        "fields": fields,
        "footer": {"text": f"Orithena Pulse | {item.get('published_at', '')[:10]}"},
    }

    return embed


def post_signals(webhook_url: str, top_n: int = 10, dry_run: bool = False) -> int:
    """Post top scored signals to Discord. Returns count posted."""
    scored_items = load_scored()
    if not scored_items:
        logger.info("No scored items to post")
        return 0

    # Filter to items that passed threshold, sort by score descending
    passed = [s for s in scored_items if s.get("passed_threshold")]
    passed.sort(key=lambda s: s.get("score", 0), reverse=True)

    posted = load_posted()
    new_items = [
        s for s in passed
        if s.get("item", {}).get("source_id") and s["item"]["source_id"] not in posted
    ]

    # Take top N
    to_post = new_items[:top_n]

    if not to_post:
        logger.info("No new signals to post (%d already posted)", len(posted))
        return 0

    logger.info("Found %d new signals to post (top %d)", len(to_post), top_n)

    count = 0
    for scored in to_post:
        embed = build_embed(scored)
        source_id = scored["item"]["source_id"]

        if dry_run:
            logger.info("[DRY RUN] Would post: %s (score: %.1f)", scored["item"].get("title"), scored.get("score", 0))
            count += 1
            continue

        payload = {"embeds": [embed]}
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.status_code in (200, 204):
                posted.add(source_id)
                count += 1
                logger.info("Posted: %s (score: %.1f)", scored["item"].get("title"), scored.get("score", 0))
            elif resp.status_code == 429:
                retry_after = resp.json().get("retry_after", 5)
                logger.warning("Rate limited, waiting %.1fs", retry_after)
                time.sleep(retry_after)
                resp = requests.post(webhook_url, json=payload, timeout=10)
                if resp.status_code in (200, 204):
                    posted.add(source_id)
                    count += 1
            else:
                logger.error("Failed to post %s: HTTP %d", scored["item"].get("title"), resp.status_code)
        except requests.RequestException as e:
            logger.error("Error posting %s: %s", scored["item"].get("title"), e)

        time.sleep(0.5)

    if not dry_run:
        save_posted(posted)

    logger.info("Posted %d/%d new signals", count, len(to_post))
    return count


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Post signals to Discord")
    parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    parser.add_argument("--top", type=int, default=10, help="Number of top items to post (default: 10)")
    args = parser.parse_args()

    webhook_url = os.environ.get("DISCORD_WEBHOOK_PULSE")
    if not webhook_url:
        logger.warning("DISCORD_WEBHOOK_PULSE not set, skipping Discord posting")
        return

    post_signals(webhook_url, top_n=args.top, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
