"""Per-item structured report generator.

Phase 1: Rule-based report generation without LLM calls.
Extracts structured intelligence from scored items using keyword matching,
description parsing, and domain configuration.
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from config import REPORTS_DIR
from models import ContentItem, ScoredItem, IntelReport

logger = logging.getLogger(__name__)

# Indicators of novelty in content descriptions
NOVELTY_INDICATORS = [
    "novel",
    "new approach",
    "first",
    "outperforms",
    "state-of-the-art",
    "introduces",
    "breakthrough",
    "unprecedented",
    "surpasses",
    "pioneering",
]


def _truncate_to_sentences(text: str, max_sentences: int = 3) -> str:
    """Truncate text to the first N sentences.

    Args:
        text: The input text to truncate.
        max_sentences: Maximum number of sentences to keep.

    Returns:
        The truncated text, or the original if it has fewer sentences.
    """
    # Split on sentence-ending punctuation followed by whitespace
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    kept = sentences[:max_sentences]
    result = " ".join(kept)
    # Ensure it ends with punctuation
    if result and result[-1] not in ".!?":
        result += "."
    return result


def _extract_novelty(description: str) -> str:
    """Scan description for novelty indicators and generate a statement.

    Args:
        description: The item's description text.

    Returns:
        A sentence describing what is novel, or a default statement.
    """
    if not description:
        return "No explicit novelty claims. May represent incremental work."

    text_lower = description.lower()
    found = [indicator for indicator in NOVELTY_INDICATORS if indicator in text_lower]

    if not found:
        return "No explicit novelty claims. May represent incremental work."

    # Build a novelty statement from matched indicators
    indicator_str = ", ".join(f'"{ind}"' for ind in found[:3])
    return (
        f"Content signals novelty via {indicator_str}. "
        f"Review the source material for specific claims and evidence."
    )


def _match_focus_areas(item: ContentItem, domain_config: dict) -> list[str]:
    """Find which focus areas from the domain config match this item.

    Args:
        item: The content item to check.
        domain_config: The full domain configuration dict.

    Returns:
        List of matched focus area names.
    """
    focus_areas = domain_config.get("analysis", {}).get("focus_areas", [])
    text = f"{item.title} {item.description or ''}".lower()

    matched = []
    for area in focus_areas:
        keywords = area.get("keywords", [])
        hits = sum(1 for kw in keywords if kw.lower() in text)
        if hits >= 1:
            matched.append(area["area"])

    return matched


def _build_relevance(matched_areas: list[str]) -> str:
    """Build a relevance statement from matched focus areas.

    Args:
        matched_areas: List of focus area names that matched.

    Returns:
        A relevance statement string.
    """
    if not matched_areas:
        return "No direct match to tracked focus areas. May have tangential relevance."

    return f"Relevant to: {', '.join(matched_areas)}"


def _determine_action(score: float) -> str:
    """Determine recommended action based on score thresholds.

    Phase 1 only assigns 'investigate' and 'watch'. The 'adopt' and 'ignore'
    actions are reserved for LLM rescoring (Phase 1.5+) or human override.

    Args:
        score: The composite score (0-10 scale).

    Returns:
        One of: "investigate", "watch".
    """
    if score >= 8.0:
        return "investigate"
    # Both 6.0-7.9 and 4.0-5.9 map to "watch" in Phase 1
    return "watch"


def _extract_key_concepts(
    item: ContentItem, domain_config: dict
) -> list[str]:
    """Extract key concepts from the item that match domain keywords.

    Looks for high_signal_keywords and focus_area keywords in the title
    and description. Returns matched keywords, deduplicated.

    Args:
        item: The content item.
        domain_config: The full domain configuration dict.

    Returns:
        List of matched keyword strings (up to 7).
    """
    text = f"{item.title} {item.description or ''}".lower()
    concepts = []
    seen = set()

    # Check high-signal keywords
    high_signal = domain_config.get("scoring", {}).get("high_signal_keywords", [])
    for kw in high_signal:
        if kw.lower() in text and kw.lower() not in seen:
            concepts.append(kw)
            seen.add(kw.lower())

    # Check focus area keywords
    focus_areas = domain_config.get("analysis", {}).get("focus_areas", [])
    for area in focus_areas:
        for kw in area.get("keywords", []):
            if kw.lower() in text and kw.lower() not in seen:
                concepts.append(kw)
                seen.add(kw.lower())

    return concepts[:7]


def _collect_links(item: ContentItem) -> list[str]:
    """Collect links for the report: primary URL plus any in metadata.

    Args:
        item: The content item.

    Returns:
        List of URL strings.
    """
    links = [item.url]

    # Check metadata for additional URLs
    for key in ("pdf_url", "html_url", "discussion_url", "repo_url"):
        url = item.metadata.get(key)
        if url and url not in links:
            links.append(url)

    return links


def generate_report(
    scored_item: ScoredItem, domain_config: dict
) -> IntelReport:
    """Generate a structured intelligence report for a scored item.

    Phase 1 implementation uses rule-based extraction without LLM calls.

    Args:
        scored_item: The scored content item.
        domain_config: The full domain configuration dict.

    Returns:
        An IntelReport populated with extracted intelligence.
    """
    item = scored_item.item

    # What it is: description truncated to 3 sentences, or title fallback
    if item.description:
        what_it_is = _truncate_to_sentences(item.description, max_sentences=3)
    else:
        what_it_is = item.title

    # Novel aspects: scan for novelty indicators
    novel_aspects = _extract_novelty(item.description)

    # Relevance: map focus areas
    matched_areas = _match_focus_areas(item, domain_config)
    relevance = _build_relevance(matched_areas)

    # Recommended action: score-based
    recommended_action = _determine_action(scored_item.score)

    # Key concepts: keyword extraction
    key_concepts = _extract_key_concepts(item, domain_config)

    # Code snippets: empty for Phase 1
    code_snippets = []

    # Links: primary URL + metadata URLs
    links = _collect_links(item)

    return IntelReport(
        item=item,
        score=scored_item.score,
        what_it_is=what_it_is,
        novel_aspects=novel_aspects,
        relevance=relevance,
        recommended_action=recommended_action,
        key_concepts=key_concepts,
        code_snippets=code_snippets,
        links=links,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _report_to_markdown(report: IntelReport) -> str:
    """Render an IntelReport as a markdown document.

    Args:
        report: The intelligence report to render.

    Returns:
        Markdown string following the standard report format.
    """
    tags_str = ", ".join(report.key_concepts) if report.key_concepts else "none"
    date_str = report.generated_at[:10] if report.generated_at else "unknown"

    lines = [
        f"# {report.item.title}",
        "",
        f"**Source:** {report.item.source} | "
        f"**Published:** {report.item.published_at[:10]} | "
        f"**Score:** {report.score}/10",
        f"**URL:** {report.item.url}",
        f"**Tags:** {tags_str}",
        "",
        "## What It Is",
        report.what_it_is,
        "",
        "## Novel Aspects",
        report.novel_aspects,
        "",
        "## Relevance to Orithena",
        report.relevance,
        "",
        "## Recommended Action",
        f"**{report.recommended_action}**",
        "",
    ]

    # Action rationale
    rationale = {
        "investigate": "High signal score warrants deeper review and analysis.",
        "watch": "Worth monitoring for developments. Review periodically.",
        "adopt": "Strong match — consider integrating into Orithena workflows.",
        "ignore": "Low relevance or insufficient signal at this time.",
    }
    lines.append(rationale.get(report.recommended_action, ""))
    lines.append("")

    lines.append("## Key Concepts")
    if report.key_concepts:
        for concept in report.key_concepts:
            lines.append(f"- {concept}")
    else:
        lines.append("- No specific concepts extracted")
    lines.append("")

    if report.code_snippets:
        lines.append("## Code Snippets")
        for snippet in report.code_snippets:
            lines.append(f"```\n{snippet}\n```")
        lines.append("")

    lines.append("## Links")
    for link in report.links:
        lines.append(f"- {link}")
    lines.append("")

    lines.append("---")
    lines.append(f"*Generated by Orithena Pulse on {date_str}*")
    lines.append("")

    return "\n".join(lines)


def save_report(report: IntelReport, date_str: str) -> Path:
    """Save an intelligence report to disk as markdown.

    Writes to REPORTS_DIR/{date}/{slug}.md.

    Args:
        report: The intelligence report to save.
        date_str: Date string (YYYY-MM-DD) for the subdirectory.

    Returns:
        Path to the written file.
    """
    report_dir = REPORTS_DIR / date_str
    report_dir.mkdir(parents=True, exist_ok=True)

    slug = report.item.slug
    output_path = report_dir / f"{slug}.md"

    markdown = _report_to_markdown(report)
    output_path.write_text(markdown, encoding="utf-8")

    logger.info("Saved report: %s", output_path)
    return output_path
