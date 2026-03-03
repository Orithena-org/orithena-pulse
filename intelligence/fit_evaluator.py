"""Orithena Fit evaluator — uses Claude API to score items against org vision.

Evaluates each item for relevance to Orithena's products and generates:
- why_unique: what makes this item stand out
- orithena_fit: structured fit assessment (relevant, product, sketch, score)

Degrades gracefully if the API is unavailable (placeholder score of 5).
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

from models import ScoredItem

logger = logging.getLogger(__name__)

# Load org vision doc once at import time
_VISION_PATH = Path(__file__).parent.parent / "orithena-org-vision.md"
_VISION_TEXT = ""
if _VISION_PATH.exists():
    _VISION_TEXT = _VISION_PATH.read_text(encoding="utf-8")
else:
    logger.warning("Org vision doc not found at %s", _VISION_PATH)


def _build_prompt(item: ScoredItem) -> str:
    """Build the evaluation prompt for a single item."""
    meta_parts = []
    if item.item.source == "hn":
        meta_parts.append(f"HN points: {item.item.metadata.get('points', 0)}")
    elif item.item.source == "github_trending":
        meta_parts.append(f"Stars: {item.item.metadata.get('stars', 0)}")
    elif item.item.source == "arxiv":
        cats = item.item.metadata.get("categories", [])
        if cats:
            meta_parts.append(f"Categories: {', '.join(cats)}")
    meta_str = " | ".join(meta_parts) if meta_parts else "none"

    return f"""You are evaluating a content item for the Orithena organization.

<org_vision>
{_VISION_TEXT}
</org_vision>

<item>
Title: {item.item.title}
Source: {item.item.source}
Type: {item.item.content_type}
URL: {item.item.url}
Metadata: {meta_str}
Description: {item.item.description or 'No description available.'}
</item>

Respond with ONLY valid JSON (no markdown fences, no commentary) matching this schema:
{{
  "why_unique": "1-2 sentences on what makes this item stand out — not a summary, but what's genuinely novel or noteworthy",
  "relevant": true/false,
  "relevant_why": "1 sentence explaining why or why not",
  "product": "madison-events" | "orithena-pulse" | "both" | "neither",
  "implementation_sketch": "1-3 sentences of a high-level implementation idea, or 'not applicable'",
  "fit_score": <integer 1-10, where 10 = build immediately>
}}"""


def _call_claude_api(prompt: str) -> Optional[dict]:
    """Call the Claude API and parse the JSON response.

    Returns parsed dict on success, None on any failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping LLM fit evaluation")
        return None

    try:
        import anthropic
    except ImportError:
        # Fall back to raw HTTP if anthropic SDK not installed
        return _call_claude_http(api_key, prompt)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        return json.loads(text)
    except Exception as exc:
        logger.warning("Claude API call failed: %s", exc)
        return None


def _call_claude_http(api_key: str, prompt: str) -> Optional[dict]:
    """Fallback: call Claude API via raw HTTP (no SDK dependency)."""
    import urllib.request

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["content"][0]["text"].strip()
            return json.loads(text)
    except Exception as exc:
        logger.warning("Claude HTTP API call failed: %s", exc)
        return None


def _placeholder_fit() -> dict:
    """Return a placeholder fit result when API is unavailable."""
    return {
        "why_unique": "API unavailable — uniqueness not evaluated.",
        "relevant": False,
        "relevant_why": "API unavailable",
        "product": "neither",
        "implementation_sketch": "not applicable",
        "fit_score": 5,
    }


def evaluate_fit(item: ScoredItem) -> dict:
    """Evaluate a single item's fit with Orithena.

    Returns a dict with keys: why_unique, relevant, relevant_why,
    product, implementation_sketch, fit_score.

    Degrades gracefully — returns placeholder data if API fails.
    """
    if not _VISION_TEXT:
        logger.warning("No org vision loaded — using placeholder fit")
        return _placeholder_fit()

    prompt = _build_prompt(item)
    result = _call_claude_api(prompt)

    if result is None:
        return _placeholder_fit()

    # Validate and sanitize the response
    try:
        fit = {
            "why_unique": str(result.get("why_unique", "Not evaluated.")),
            "relevant": bool(result.get("relevant", False)),
            "relevant_why": str(result.get("relevant_why", "Not evaluated.")),
            "product": str(result.get("product", "neither")),
            "implementation_sketch": str(
                result.get("implementation_sketch", "not applicable")
            ),
            "fit_score": max(1, min(10, int(result.get("fit_score", 5)))),
        }
        return fit
    except (ValueError, TypeError) as exc:
        logger.warning("Failed to parse fit response: %s", exc)
        return _placeholder_fit()


def evaluate_fits(items: list) -> Dict[str, dict]:
    """Evaluate fit for all items. Returns a dict keyed by item slug.

    Calls the API for each item sequentially. If the first call fails
    (no API key, network error), skips remaining items and returns
    placeholders for all.
    """
    results = {}  # type: Dict[str, dict]
    api_available = True

    for item in items:
        slug = item.item.slug
        if not api_available:
            results[slug] = _placeholder_fit()
            continue

        fit = evaluate_fit(item)
        # If the first result is a placeholder, assume API is down
        if fit["relevant_why"] == "API unavailable" and not results:
            api_available = False
            logger.info("API unavailable — using placeholders for all items")
        results[slug] = fit

    logger.info("Evaluated fit for %d items (API available: %s)",
                len(results), api_available)
    return results
