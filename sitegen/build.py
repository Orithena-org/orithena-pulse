"""Static site generator for Orithena Pulse daily digests."""

import logging
import shutil
from pathlib import Path
from datetime import datetime
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader

from config import SITE_DIR, SITE_TITLE, SITE_URL, BASE_PATH, DATA_DIR, PROJECT_ROOT
from models import ScoredItem

logger = logging.getLogger(__name__)

TEMPLATES_DIR = PROJECT_ROOT / "sitegen" / "templates"
STATIC_DIR = PROJECT_ROOT / "sitegen" / "static"


def _format_metadata(item: ScoredItem) -> str:
    """Build a human-readable metadata string for a scored item.

    Examples:
        "hn - 142 points"
        "arxiv - cs.AI"
        "github - 1.2k stars"
    """
    ci = item.item
    source = ci.source
    meta = ci.metadata

    if source == "hn":
        points = meta.get("points", 0)
        return f"hn \u00b7 {points} points"
    elif source == "arxiv":
        categories = meta.get("categories", [])
        if categories:
            cat_str = ", ".join(categories[:3])
            return f"arxiv \u00b7 {cat_str}"
        return "arxiv"
    elif source in ("github", "github_trending"):
        stars = meta.get("stars", 0)
        if stars >= 1000:
            return f"github \u00b7 \u2605{stars / 1000:.1f}k"
        return f"github \u00b7 \u2605{stars}"
    elif source == "rss":
        feed_name = meta.get("feed_name", "rss")
        return feed_name
    else:
        return source


def _truncate(text, max_len: int = 150) -> str:
    """Truncate text to max_len characters, adding ellipsis if needed."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "\u2026"


def _group_into_sections(
    scored_items: list[ScoredItem], domain_config: dict
) -> list[dict]:
    """Group scored items into display sections based on domain config.

    Each section dict has keys: name, items.
    Uses domain_config["site"]["sections"] if available, otherwise falls back
    to the default section definitions.
    """
    # Sort all items by score descending for Top Signal selection
    sorted_items = sorted(scored_items, key=lambda s: s.score, reverse=True)

    sections_config = (
        domain_config.get("site", {}).get("sections")
        if domain_config
        else None
    )

    # Per-section count limits from config (default 5)
    section_counts = {}
    if sections_config:
        for sc in sections_config:
            section_counts[sc["name"]] = sc.get("count", 5)

    top_signal_count = section_counts.get("Top Signal", 5)
    sections: list[dict] = []

    # --- High Signal: items with fit_score >= 7 (shown first) ---
    high_signal_items = [si for si in sorted_items if si.high_signal]
    high_signal_ids = set()
    if high_signal_items:
        high_signal_ids = {id(si) for si in high_signal_items}
        sections.append({"name": "High Signal", "items": high_signal_items})

    # --- Top Signal: top N by score (excluding high-signal items) ---
    top_items = [
        si for si in sorted_items if id(si) not in high_signal_ids
    ][:top_signal_count]
    top_ids = {id(si) for si in top_items} | high_signal_ids
    sections.append({"name": "Top Signal", "items": top_items})

    # --- Papers ---
    max_papers = section_counts.get("Papers", 5)
    papers = [
        si
        for si in sorted_items
        if si.item.content_type == "paper" and id(si) not in top_ids
    ][:max_papers]
    if papers:
        sections.append({"name": "Papers", "items": papers})

    # --- Launches & Repos ---
    max_launches = section_counts.get("Launches & Repos", 5)
    launches = [
        si
        for si in sorted_items
        if si.item.content_type in ("repo", "launch") and id(si) not in top_ids
    ][:max_launches]
    if launches:
        sections.append({"name": "Launches & Repos", "items": launches})

    # --- Discussion ---
    max_discussion = section_counts.get("Discussion", 5)
    discussion = [
        si
        for si in sorted_items
        if si.item.content_type in ("article", "discussion")
        and id(si) not in top_ids
    ][:max_discussion]
    if discussion:
        sections.append({"name": "Discussion", "items": discussion})

    return sections


def _build_archive_index(date_str: str) -> list[str]:
    """Scan the archive/ directory in SITE_DIR and return sorted date strings.

    Returns dates in reverse chronological order (newest first).
    Ensures the current date_str is included even if its file hasn't been
    written yet.
    """
    archive_dir = SITE_DIR / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    dates: set[str] = set()
    for path in archive_dir.glob("*.html"):
        # Files are named like 2026-03-02.html
        stem = path.stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            dates.add(stem)

    dates.add(date_str)
    return sorted(dates, reverse=True)


def _build_rss_feed(
    sections: list[dict],
    date_str: str,
    domain_config: dict,
) -> str:
    """Generate an RSS 2.0 XML feed string for the current digest."""
    site_title = SITE_TITLE
    site_url = SITE_URL
    tagline = domain_config.get("site", {}).get("tagline", "Daily AI signal digest")
    build_date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")

    items_xml = []
    for section in sections:
        for si in section["items"]:
            ci = si.item
            desc = _truncate(ci.description, 300)
            items_xml.append(
                f"    <item>\n"
                f"      <title>{xml_escape(ci.title)}</title>\n"
                f"      <link>{xml_escape(ci.url)}</link>\n"
                f"      <description>{xml_escape(desc)}</description>\n"
                f"      <pubDate>{xml_escape(ci.published_at)}</pubDate>\n"
                f"      <guid>{xml_escape(ci.url)}</guid>\n"
                f"    </item>"
            )

    items_str = "\n".join(items_xml)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{xml_escape(site_title)}</title>\n"
        f"    <link>{xml_escape(site_url)}</link>\n"
        f"    <description>{xml_escape(tagline)}</description>\n"
        f"    <lastBuildDate>{build_date}</lastBuildDate>\n"
        f'    <atom:link href="{xml_escape(site_url + "/feed.xml")}" '
        f'rel="self" type="application/rss+xml"/>\n'
        f"{items_str}\n"
        "  </channel>\n"
        "</rss>\n"
    )


def build_site(
    scored_items: list[ScoredItem],
    domain_config: dict,
    date_str: str,
) -> None:
    """Build the full static site from scored items.

    Generates:
        - index.html (latest digest, same content as today's archive page)
        - archive/{date_str}.html (today's digest)
        - archive.html (listing of all digest dates)
        - about.html (static about page)
        - feed.xml (RSS feed)
        - css/ and js/ static assets
        - .nojekyll (for GitHub Pages)

    Args:
        scored_items: List of ScoredItem objects that passed the quality threshold.
        domain_config: Parsed domain YAML configuration dict.
        date_str: Date string in YYYY-MM-DD format for today's digest.
    """
    logger.info("Building site for %s with %d items", date_str, len(scored_items))

    # Ensure output directory exists
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    # Set up Jinja2 environment
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Register custom filters
    env.filters["truncate_desc"] = _truncate
    env.filters["format_meta"] = _format_metadata

    # Group items into sections
    sections = _group_into_sections(scored_items, domain_config)

    # Template context shared across pages
    site_config = domain_config.get("site", {}) if domain_config else {}
    base_context = {
        "site_title": SITE_TITLE,
        "site_url": SITE_URL,
        "base_path": BASE_PATH,
        "tagline": site_config.get("tagline", "Daily AI signal digest"),
        "date_str": date_str,
    }

    # --- Render index.html (latest digest) ---
    index_template = env.get_template("index.html")
    index_html = index_template.render(
        **base_context,
        sections=sections,
    )
    (SITE_DIR / "index.html").write_text(index_html, encoding="utf-8")
    logger.info("Wrote index.html")

    # --- Render archive/{date_str}.html ---
    archive_dir = SITE_DIR / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_page = index_template.render(
        **base_context,
        sections=sections,
    )
    (archive_dir / f"{date_str}.html").write_text(archive_page, encoding="utf-8")
    logger.info("Wrote archive/%s.html", date_str)

    # --- Build and render archive.html (index of all dates) ---
    archive_dates = _build_archive_index(date_str)
    archive_index_template = env.get_template("archive.html")
    archive_index_html = archive_index_template.render(
        **base_context,
        dates=archive_dates,
    )
    (SITE_DIR / "archive.html").write_text(archive_index_html, encoding="utf-8")
    logger.info("Wrote archive.html with %d dates", len(archive_dates))

    # --- Render about.html ---
    about_template = env.get_template("about.html")
    about_html = about_template.render(**base_context)
    (SITE_DIR / "about.html").write_text(about_html, encoding="utf-8")
    logger.info("Wrote about.html")

    # --- Generate RSS feed ---
    rss_xml = _build_rss_feed(sections, date_str, domain_config)
    (SITE_DIR / "feed.xml").write_text(rss_xml, encoding="utf-8")
    logger.info("Wrote feed.xml")

    # --- Copy static assets ---
    static_dest = SITE_DIR / "css"
    if static_dest.exists():
        shutil.rmtree(static_dest)
    shutil.copytree(STATIC_DIR / "css", static_dest)

    js_dest = SITE_DIR / "js"
    if js_dest.exists():
        shutil.rmtree(js_dest)
    shutil.copytree(STATIC_DIR / "js", js_dest)
    logger.info("Copied static assets (css/, js/)")

    # --- Create .nojekyll for GitHub Pages ---
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    logger.info("Site build complete: %s", SITE_DIR)
