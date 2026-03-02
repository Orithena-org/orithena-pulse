"""Rolling digest generator for Orithena Pulse.

Produces a daily markdown digest summarizing all scored items,
organized by section: action items, top signal, papers, repos/launches,
and keyword trends.
"""

import logging
from collections import Counter

from models import ScoredItem

logger = logging.getLogger(__name__)


def _keyword_trends(
    items: list[ScoredItem], domain_config: dict
) -> str:
    """Count high-signal keyword frequency across all items and report top 5.

    Args:
        items: List of scored items to analyze.
        domain_config: The full domain configuration dict.

    Returns:
        Markdown-formatted string of keyword trends, or a fallback message.
    """
    high_signal = domain_config.get("scoring", {}).get("high_signal_keywords", [])
    if not high_signal:
        return "No trend keywords configured."

    counter = Counter()
    for scored in items:
        text = (
            f"{scored.item.title} {scored.item.description or ''}"
        ).lower()
        for kw in high_signal:
            if kw.lower() in text:
                counter[kw] += 1

    if not counter:
        return "No significant keyword trends detected today."

    top = counter.most_common(5)
    lines = []
    for keyword, count in top:
        lines.append(f"- **{keyword}**: {count} item{'s' if count != 1 else ''}")
    return "\n".join(lines)


def _format_action_items(items: list[ScoredItem]) -> str:
    """Format items scoring 8.0+ as action items.

    Args:
        items: List of scored items (pre-filtered to passed_threshold).

    Returns:
        Markdown-formatted action items section.
    """
    action_items = [s for s in items if s.score >= 8.0]
    if not action_items:
        return "No high-priority items today."

    lines = []
    for scored in sorted(action_items, key=lambda s: s.score, reverse=True):
        lines.append(
            f"- **[{scored.score}]** [{scored.item.title}]({scored.item.url}) "
            f"({scored.item.source})"
        )
    return "\n".join(lines)


def _format_top_signal(items: list[ScoredItem], limit: int = 5) -> str:
    """Format the top N items with 1-line summaries and scores.

    Args:
        items: List of scored items (pre-filtered to passed_threshold).
        limit: Maximum number of items to include.

    Returns:
        Markdown-formatted top signal section.
    """
    top = sorted(items, key=lambda s: s.score, reverse=True)[:limit]
    if not top:
        return "No items passed curation today."

    lines = []
    for scored in top:
        summary = scored.item.description or scored.item.title
        # Truncate to first sentence for 1-liner
        first_sentence = summary.split(". ")[0]
        if len(first_sentence) > 150:
            first_sentence = first_sentence[:147] + "..."
        if not first_sentence.endswith("."):
            first_sentence += "."
        lines.append(
            f"- **[{scored.score}]** [{scored.item.title}]({scored.item.url}) "
            f"-- {first_sentence}"
        )
    return "\n".join(lines)


def _format_notable_papers(items: list[ScoredItem]) -> str:
    """Format arxiv papers that passed curation.

    Args:
        items: List of scored items (pre-filtered to passed_threshold).

    Returns:
        Markdown-formatted papers section.
    """
    papers = [s for s in items if s.item.source == "arxiv"]
    if not papers:
        return "No notable papers today."

    lines = []
    for scored in sorted(papers, key=lambda s: s.score, reverse=True):
        categories = scored.item.metadata.get("categories", "")
        if isinstance(categories, list):
            categories = ", ".join(categories)
        cat_str = f" ({categories})" if categories else ""
        lines.append(
            f"- [{scored.item.title}]({scored.item.url}){cat_str} "
            f"[{scored.score}]"
        )
    return "\n".join(lines)


def _format_repos_and_launches(items: list[ScoredItem]) -> str:
    """Format GitHub repos and Show HN/launch items.

    Args:
        items: List of scored items (pre-filtered to passed_threshold).

    Returns:
        Markdown-formatted repos and launches section.
    """
    repos = [
        s for s in items
        if s.item.content_type in ("repo", "launch")
        or s.item.source == "github_trending"
    ]
    if not repos:
        return "No new repos or launches today."

    lines = []
    for scored in sorted(repos, key=lambda s: s.score, reverse=True):
        meta = scored.item.metadata
        if scored.item.source == "github_trending":
            stars = meta.get("stars", 0)
            star_str = f" ({stars} stars)" if stars else ""
            lines.append(
                f"- [{scored.item.title}]({scored.item.url}){star_str} "
                f"-- {scored.item.description or 'No description'}"
            )
        else:
            points = meta.get("points", "")
            points_str = f" ({points} points)" if points else ""
            lines.append(
                f"- [{scored.item.title}]({scored.item.url}){points_str} "
                f"-- {scored.item.description or scored.item.title}"
            )
    return "\n".join(lines)


def generate_digest(
    scored_items: list[ScoredItem],
    domain_config: dict,
    date_str: str,
) -> str:
    """Generate a full markdown digest from scored items.

    Args:
        scored_items: All scored items from the pipeline run (both passed
            and failed). Only passed items are included in the digest body.
        domain_config: The full domain configuration dict.
        date_str: Date string (YYYY-MM-DD) for the digest header.

    Returns:
        Complete markdown string for the daily digest.
    """
    domain_name = domain_config.get("name", "Unknown Domain")
    n_total = len(scored_items)
    passed = [s for s in scored_items if s.passed_threshold]
    n_passed = len(passed)
    n_top = len([s for s in passed if s.score >= 8.0])

    sections = [
        f"# Pulse Intelligence Digest -- {date_str}",
        "",
        f"**Domain:** {domain_name}",
        f"**Items Processed:** {n_total} | "
        f"**Passed Curation:** {n_passed} | "
        f"**Top Signal:** {n_top}",
        "",
        "## Action Items",
        _format_action_items(passed),
        "",
        "## Top Signal",
        _format_top_signal(passed),
        "",
        "## Notable Papers",
        _format_notable_papers(passed),
        "",
        "## New Repos & Launches",
        _format_repos_and_launches(passed),
        "",
        "## Trends",
        _keyword_trends(passed, domain_config),
        "",
        "## Full Reports",
        f"See individual reports in `data/reports/{date_str}/`.",
        "",
        "---",
        "*Generated by Orithena Pulse pipeline*",
        "",
    ]

    digest = "\n".join(sections)
    logger.info(
        "Generated digest: %d total, %d passed, %d top signal",
        n_total,
        n_passed,
        n_top,
    )
    return digest
