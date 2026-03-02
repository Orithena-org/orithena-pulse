"""Rule-based content scoring engine for Pulse."""

import re
from datetime import datetime, timezone
from typing import Optional

from models import ContentItem, ScoredItem


def _clamp(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, value))


def _parse_iso_datetime(iso_str: str) -> Optional[datetime]:
    """Parse an ISO 8601 datetime string, returning None on failure."""
    if not iso_str:
        return None
    try:
        # Handle various ISO formats
        iso_str = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None


def _hours_since(iso_str: str) -> Optional[float]:
    """Return hours elapsed since the given ISO 8601 timestamp, or None."""
    dt = _parse_iso_datetime(iso_str)
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    return delta.total_seconds() / 3600.0


def _text_blob(item: ContentItem) -> str:
    """Return a searchable text blob from title + description, lowercased."""
    parts = [item.title or ""]
    if item.description:
        parts.append(item.description)
    return " ".join(parts).lower()


def _score_novelty(
    item: ContentItem,
    scoring_config: dict,
    seen_urls: Optional[set[str]],
) -> float:
    """Score novelty (0-10).

    - Baseline: 5.0
    - +2.0 if published < 6 hours ago
    - +1.0 if published < 12 hours ago (and not already getting the +2)
    - -5.0 if URL was seen before
    - +1.5 if title/description suggests a launch or new repo
    - +1.0 if content_type is paper or source is arxiv
    """
    score = 5.0

    # Recency bonus
    hours = _hours_since(item.published_at)
    if hours is not None:
        if hours < 6:
            score += 2.0
        elif hours < 12:
            score += 1.0

    # Seen penalty
    if seen_urls and item.normalized_url in seen_urls:
        score -= 5.0

    # Launch / repo detection
    text = _text_blob(item)
    launch_patterns = [
        r"\blaunch\b", r"\breleased?\b", r"\bannouncing\b", r"\bintroducing\b",
        r"\bnew repo\b", r"\bopen.?source\b", r"\bv\d+\.\d+\b",
    ]
    for pattern in launch_patterns:
        if re.search(pattern, text):
            score += 1.5
            break

    # Paper bonus
    if item.content_type == "paper" or item.source == "arxiv":
        score += 1.0

    return _clamp(score)


def _score_relevance(
    item: ContentItem,
    scoring_config: dict,
    focus_areas: list[dict],
) -> float:
    """Score relevance (0-10) via keyword matching.

    - high_signal_keywords: +1.5 each
    - noise_keywords: -3.0 each
    - Focus area matching: +1.0 if >= 2 keyword hits from any single focus area
    """
    score = 0.0
    text = _text_blob(item)

    # High-signal keyword matches
    high_signal = scoring_config.get("high_signal_keywords", [])
    for kw in high_signal:
        if kw.lower() in text:
            score += 1.5

    # Noise keyword penalties
    noise = scoring_config.get("noise_keywords", [])
    for kw in noise:
        if kw.lower() in text:
            score -= 3.0

    # Focus area bonus
    for area in focus_areas:
        keywords = area.get("keywords", [])
        hits = sum(1 for kw in keywords if kw.lower() in text)
        if hits >= 2:
            score += 1.0

    return _clamp(score)


def _score_signal_quality(
    item: ContentItem,
    scoring_config: dict,
) -> float:
    """Score signal quality (0-10).

    - Baseline: 5.0
    - Description length bonuses:
      - +2.0 if > 500 chars
      - +1.0 if > 200 chars (and not already getting +2)
      - -2.0 if < 50 chars
    - Multiply by source_trust factor
    """
    score = 5.0

    desc_len = len(item.description) if item.description else 0
    if desc_len > 500:
        score += 2.0
    elif desc_len > 200:
        score += 1.0
    elif desc_len < 50:
        score -= 2.0

    # Apply source trust multiplier
    source_trust = scoring_config.get("source_trust", {})
    trust = source_trust.get(item.source, 1.0)
    score *= trust

    return _clamp(score)


def _score_engagement(
    item: ContentItem,
    scoring_config: dict,
) -> float:
    """Score engagement (0-10).

    - HN: points/50 + comments/20
    - GitHub: stars/100
    - arxiv / rss: 3.0 baseline
    """
    meta = item.metadata or {}

    if item.source == "hn":
        points = meta.get("points", 0) or 0
        comments = meta.get("num_comments", 0) or 0
        score = points / 50.0 + comments / 20.0
    elif item.source == "github_trending":
        stars = meta.get("stars", 0) or 0
        score = stars / 100.0
    else:
        # arxiv, rss, and other sources get a baseline
        score = 3.0

    return _clamp(score)


def extract_tags(item: ContentItem, focus_areas: list[dict]) -> list[str]:
    """Return a list of matched focus area names for the given item.

    A focus area matches if at least one of its keywords appears in the
    item's title or description.
    """
    text = _text_blob(item)
    tags = []
    for area in focus_areas:
        name = area.get("area", area.get("name", ""))
        keywords = area.get("keywords", [])
        if any(kw.lower() in text for kw in keywords):
            tags.append(name)
    return tags


def score_item(
    item: ContentItem,
    domain_config: dict,
    seen_urls: Optional[set[str]] = None,
) -> ScoredItem:
    """Score a single ContentItem using the rule-based scoring engine.

    Args:
        item: The content item to score.
        domain_config: Domain configuration dict containing "scoring" and
            "analysis" sections.
        seen_urls: Optional set of previously-seen normalized URLs for
            novelty scoring.

    Returns:
        A ScoredItem with component scores and composite score.
    """
    scoring_config = domain_config.get("scoring", {})
    analysis_config = domain_config.get("analysis", {})
    focus_areas = analysis_config.get("focus_areas", [])

    # Compute component scores
    novelty = _score_novelty(item, scoring_config, seen_urls)
    relevance = _score_relevance(item, scoring_config, focus_areas)
    signal_quality = _score_signal_quality(item, scoring_config)
    engagement = _score_engagement(item, scoring_config)

    scores = {
        "novelty": round(novelty, 2),
        "relevance": round(relevance, 2),
        "signal_quality": round(signal_quality, 2),
        "engagement": round(engagement, 2),
    }

    # Weighted composite
    weights = scoring_config.get("weights", {
        "novelty": 0.3,
        "relevance": 0.3,
        "signal_quality": 0.2,
        "engagement": 0.2,
    })
    composite = (
        novelty * weights.get("novelty", 0.3)
        + relevance * weights.get("relevance", 0.3)
        + signal_quality * weights.get("signal_quality", 0.2)
        + engagement * weights.get("engagement", 0.2)
    )
    composite = _clamp(composite)

    # Threshold check
    threshold = scoring_config.get("min_score", 4.0)
    passed = composite >= threshold

    # Tags
    tags = extract_tags(item, focus_areas)

    return ScoredItem(
        item=item,
        score=round(composite, 2),
        scores=scores,
        passed_threshold=passed,
        tags=tags,
    )


def score_items(
    items: list[ContentItem],
    domain_config: dict,
) -> list[ScoredItem]:
    """Score all items and return them sorted by composite score descending.

    Builds a seen_urls set from all items to enable novelty deduplication
    within the batch.

    Args:
        items: List of ContentItems to score.
        domain_config: Domain configuration dict.

    Returns:
        List of ScoredItems sorted by score (highest first).
    """
    seen_urls: set[str] = set()
    scored: list[ScoredItem] = []

    for item in items:
        result = score_item(item, domain_config, seen_urls)
        scored.append(result)
        seen_urls.add(item.normalized_url)

    scored.sort(key=lambda s: s.score, reverse=True)
    return scored
