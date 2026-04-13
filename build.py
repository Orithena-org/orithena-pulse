#!/usr/bin/env python3
"""Standalone site builder for Orithena Pulse.

Reads output/data/items.json (written by the orithena-org content pipeline)
and renders the site using Jinja2 templates. No dependency on orithena-org.

Usage:
    python build.py
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "output" / "data" / "items.json"
TEMPLATES_DIR = ROOT / "sitegen" / "templates"
STATIC_DIR = ROOT / "sitegen" / "static"
SITE_DIR = ROOT / "_site"

# Defaults — can be overridden via env vars
SITE_TITLE = os.environ.get("PULSE_SITE_TITLE", "Orithena Pulse: Agentic AI")
SITE_URL = os.environ.get("PULSE_SITE_URL", "")
TAGLINE = os.environ.get("PULSE_TAGLINE",
                         "Daily intelligence on AI agents, memory, orchestration, and tool use")
GOATCOUNTER_SITE = os.environ.get("PULSE_GOATCOUNTER_SITE", "georgeauto")


class AttrDict(dict):
    """Dict subclass that supports attribute access (for Jinja2 templates)."""
    def __getattr__(self, key):
        try:
            val = self[key]
        except KeyError:
            return ""
        if isinstance(val, dict) and not isinstance(val, AttrDict):
            val = AttrDict(val)
            self[key] = val
        return val


def _wrap(d: dict) -> AttrDict:
    """Recursively wrap a dict for attribute access."""
    return AttrDict(d)


def _truncate(text, max_len: int = 150) -> str:
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len - 1].rstrip() + "\u2026"


def _format_metadata(si) -> str:
    """Format source metadata for display."""
    if isinstance(si, dict):
        ci = si.get("item", {})
    else:
        ci = getattr(si, "item", {})

    if isinstance(ci, dict):
        source = ci.get("source", "")
        meta = ci.get("metadata", {})
    else:
        source = getattr(ci, "source", "")
        meta = getattr(ci, "metadata", {})

    if isinstance(meta, dict):
        pass
    else:
        meta = {}

    if source == "hn":
        return f"hn \u00b7 {meta.get('points', 0)} points"
    elif source == "arxiv":
        categories = meta.get("categories", [])
        return f"arxiv \u00b7 {', '.join(categories[:3])}" if categories else "arxiv"
    elif source in ("github", "github_trending"):
        stars = meta.get("stars", 0)
        return f"github \u00b7 \u2605{stars / 1000:.1f}k" if stars >= 1000 else f"github \u00b7 \u2605{stars}"
    elif source == "rss":
        return meta.get("feed_name", "rss")
    return source


def _load_data() -> dict:
    """Load the items data JSON."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Data file not found: {DATA_FILE}")
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _build_sections(items: list[AttrDict]) -> list[dict]:
    """Group items into display sections (mirrors orithena-org sitegen logic)."""
    sorted_items = sorted(items, key=lambda s: s.get("score", 0), reverse=True)

    sections = []
    high_signal = [si for si in sorted_items if si.get("high_signal")]
    if high_signal:
        sections.append({"name": "High Signal", "items": high_signal})

    hs_ids = {id(si) for si in high_signal}
    top_items = [si for si in sorted_items if id(si) not in hs_ids][:5]
    sections.append({"name": "Top Signal", "items": top_items})
    used_ids = hs_ids | {id(si) for si in top_items}

    for sec_name, content_types in [
        ("Papers", ["paper"]),
        ("Launches & Repos", ["repo", "launch"]),
        ("Discussion", ["article", "discussion"]),
    ]:
        sec_items = [
            si for si in sorted_items
            if si.get("item", {}).get("content_type") in content_types
            and id(si) not in used_ids
        ][:5]
        if sec_items:
            sections.append({"name": sec_name, "items": sec_items})

    return sections


def _build_rss_feed(sections: list[dict], date_str: str) -> str:
    build_date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    items_xml = []
    for section in sections:
        for si in section["items"]:
            ci = si.get("item", {})
            desc = _truncate(ci.get("description", ""), 300)
            items_xml.append(
                f"    <item>\n"
                f"      <title>{xml_escape(ci.get('title', ''))}</title>\n"
                f"      <link>{xml_escape(ci.get('url', ''))}</link>\n"
                f"      <description>{xml_escape(desc)}</description>\n"
                f"      <pubDate>{xml_escape(ci.get('published_at', ''))}</pubDate>\n"
                f"      <guid>{xml_escape(ci.get('url', ''))}</guid>\n"
                f"    </item>"
            )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{xml_escape(SITE_TITLE)}</title>\n"
        f"    <link>{xml_escape(SITE_URL)}</link>\n"
        f"    <description>{xml_escape(TAGLINE)}</description>\n"
        f"    <lastBuildDate>{build_date}</lastBuildDate>\n"
        f"{chr(10).join(items_xml)}\n"
        "  </channel>\n"
        "</rss>\n"
    )


def _build_sitemap(date_str: str, site_dir: Path) -> str:
    """Generate sitemap.xml listing all pages."""
    urls = [
        (f"{SITE_URL}/", date_str, "daily", "1.0"),
        (f"{SITE_URL}/about.html", date_str, "monthly", "0.3"),
        (f"{SITE_URL}/archive.html", date_str, "daily", "0.6"),
        (f"{SITE_URL}/feed.xml", date_str, "daily", "0.5"),
    ]
    # Add archive pages
    archive_dir = site_dir / "archive"
    if archive_dir.exists():
        for f in sorted(archive_dir.glob("*.html")):
            archive_date = f.stem  # e.g. 2026-03-20
            urls.append((f"{SITE_URL}/archive/{f.name}", archive_date, "never", "0.4"))

    entries = []
    for loc, lastmod, freq, priority in urls:
        entries.append(
            f"  <url>\n"
            f"    <loc>{xml_escape(loc)}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <changefreq>{freq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{chr(10).join(entries)}\n"
        "</urlset>\n"
    )


def build() -> None:
    """Build the Orithena Pulse static site from JSON data."""
    data = _load_data()
    items = [_wrap(item) for item in data["items"]]
    date_str = data.get("generated_at", "")[:10] or datetime.utcnow().strftime("%Y-%m-%d")

    print(f"Building site from {len(items)} items...")

    # Prepare output directory
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True)

    # Set up Jinja2
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["truncate_desc"] = _truncate
    env.filters["format_meta"] = _format_metadata

    base_context = {
        "site_title": SITE_TITLE,
        "site_url": SITE_URL,
        "base_path": "",
        "tagline": TAGLINE,
        "date_str": date_str,
        "goatcounter_site": GOATCOUNTER_SITE,
    }

    sections = _build_sections(items)

    # Count total items across all sections for structured data
    item_count = sum(len(s["items"]) for s in sections)

    # Render pages
    for tmpl_name, out_name, extra in [
        ("index.html", "index.html", {"sections": sections, "item_count": item_count}),
        ("about.html", "about.html", {"canonical_path": "/about.html"}),
    ]:
        try:
            tmpl = env.get_template(tmpl_name)
            html = tmpl.render(**base_context, **extra)
            (SITE_DIR / out_name).write_text(html, encoding="utf-8")
            print(f"  Wrote {out_name}")
        except Exception as e:
            print(f"  Template {tmpl_name} failed: {e}")

    # Archive landing page
    archive_dir = SITE_DIR / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    try:
        # Collect existing archive dates + today
        archive_dates = sorted(
            {f.stem for f in archive_dir.glob("*.html")} | {date_str},
            reverse=True,
        )
        tmpl = env.get_template("archive.html")
        html = tmpl.render(**base_context, dates=archive_dates, canonical_path="/archive.html")
        (SITE_DIR / "archive.html").write_text(html, encoding="utf-8")
        print("  Wrote archive.html")
    except Exception as e:
        print(f"  Template archive.html failed: {e}")

    # Archive daily digest page
    try:
        tmpl = env.get_template("index.html")
        html = tmpl.render(**base_context, sections=sections, item_count=item_count,
                           canonical_path=f"/archive/{date_str}.html")
        (archive_dir / f"{date_str}.html").write_text(html, encoding="utf-8")
        print(f"  Wrote archive/{date_str}.html")
    except Exception as e:
        print(f"  Archive digest failed: {e}")

    # RSS feed
    rss = _build_rss_feed(sections, date_str)
    (SITE_DIR / "feed.xml").write_text(rss, encoding="utf-8")

    # Sitemap
    sitemap = _build_sitemap(date_str, SITE_DIR)
    (SITE_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    print("  Wrote sitemap.xml")

    # robots.txt
    robots_lines = ["User-agent: *", "Allow: /"]
    if SITE_URL:
        robots_lines.append(f"Sitemap: {SITE_URL}/sitemap.xml")
    (SITE_DIR / "robots.txt").write_text("\n".join(robots_lines) + "\n", encoding="utf-8")
    print("  Wrote robots.txt")

    # Static assets
    if STATIC_DIR.exists():
        for subdir in ("css", "js"):
            src = STATIC_DIR / subdir
            if src.exists():
                shutil.copytree(src, SITE_DIR / subdir)

    # .nojekyll
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Site build complete: {SITE_DIR} ({len(items)} items)")


if __name__ == "__main__":
    build()
