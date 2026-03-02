"""arXiv adapter using the Atom/RSS API."""

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import REQUEST_TIMEOUT
from models import ContentItem
from scraper.base import BaseAdapter

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


class ArxivAdapter(BaseAdapter):
    """Fetches recent papers from arXiv via the Atom API."""

    name = "arxiv"

    def fetch(self) -> list[ContentItem]:
        categories = self.config["categories"]
        search_terms = self.config["search_terms"]
        max_results = self.config.get("max_results", 100)
        max_age_hours = self.config.get("max_age_hours", 48)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        now_iso = datetime.now(timezone.utc).isoformat()

        search_query = _build_search_query(categories, search_terms)
        logger.debug("arXiv search query: %s", search_query)

        items: list[ContentItem] = []
        start = 0
        batch_size = min(max_results, 100)

        while start < max_results:
            if start > 0:
                time.sleep(3)  # arXiv rate limit: 3 seconds between requests

            params = {
                "search_query": search_query,
                "start": start,
                "max_results": batch_size,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }

            try:
                resp = self.session.get(
                    ARXIV_API_URL, params=params, timeout=REQUEST_TIMEOUT
                )
                resp.raise_for_status()
            except Exception:
                logger.exception("Failed to fetch arXiv batch at start=%d", start)
                break

            root = ET.fromstring(resp.text)
            entries = root.findall(f"{ATOM_NS}entry")

            if not entries:
                break

            batch_items = _parse_entries(entries, cutoff, now_iso)
            items.extend(batch_items)

            # If we got fewer entries than requested, or all entries in this
            # batch were older than the cutoff, stop paginating.
            if len(entries) < batch_size or len(batch_items) == 0:
                break

            start += batch_size

        logger.info("arXiv adapter collected %d items", len(items))
        return items


def _build_search_query(categories: list[str], search_terms: list[str]) -> str:
    """Build an arXiv API search query from categories and search terms.

    Combines categories with OR, search terms with OR, then ANDs the two
    groups together. If one group is empty, uses only the other.
    """
    cat_parts = [f"cat:{cat}" for cat in categories]
    term_parts = [f'all:"{term}"' for term in search_terms]

    cat_clause = " OR ".join(cat_parts) if cat_parts else ""
    term_clause = " OR ".join(term_parts) if term_parts else ""

    if cat_clause and term_clause:
        return f"({cat_clause}) AND ({term_clause})"
    return cat_clause or term_clause


def _parse_entries(
    entries: list[ET.Element],
    cutoff: datetime,
    now_iso: str,
) -> list[ContentItem]:
    """Parse a list of arXiv Atom entries into ContentItem objects."""
    items: list[ContentItem] = []

    for entry in entries:
        try:
            item = _parse_single_entry(entry, cutoff, now_iso)
            if item is not None:
                items.append(item)
        except Exception:
            logger.exception("Failed to parse arXiv entry")
            continue

    return items


def _parse_single_entry(
    entry: ET.Element,
    cutoff: datetime,
    now_iso: str,
) -> Optional[ContentItem]:
    """Parse a single arXiv Atom entry, returning None if too old or invalid."""
    # Extract arXiv ID from the <id> tag (format: http://arxiv.org/abs/XXXX.XXXXX)
    id_elem = entry.find(f"{ATOM_NS}id")
    if id_elem is None or not id_elem.text:
        return None
    arxiv_url = id_elem.text.strip()
    arxiv_id = arxiv_url.rsplit("/", 1)[-1] if "/" in arxiv_url else arxiv_url

    # Published date
    published_elem = entry.find(f"{ATOM_NS}published")
    if published_elem is not None and published_elem.text:
        published_str = published_elem.text.strip()
        published_dt = _parse_arxiv_date(published_str)
        if published_dt is not None and published_dt < cutoff:
            return None
        published_at = (
            published_dt.isoformat() if published_dt else published_str
        )
    else:
        published_at = now_iso

    # Title
    title_elem = entry.find(f"{ATOM_NS}title")
    title = (title_elem.text or "").strip().replace("\n", " ") if title_elem is not None else ""
    if not title:
        return None

    # Abstract / description
    summary_elem = entry.find(f"{ATOM_NS}summary")
    description = (
        (summary_elem.text or "").strip().replace("\n", " ")
        if summary_elem is not None
        else None
    )

    # Authors
    authors = []
    for author_elem in entry.findall(f"{ATOM_NS}author"):
        name_elem = author_elem.find(f"{ATOM_NS}name")
        if name_elem is not None and name_elem.text:
            authors.append(name_elem.text.strip())

    # PDF link
    pdf_url = None
    for link_elem in entry.findall(f"{ATOM_NS}link"):
        if link_elem.get("title") == "pdf":
            pdf_url = link_elem.get("href")
            break
    if pdf_url is None:
        # Construct PDF URL from arXiv ID
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

    # Categories
    categories = []
    for cat_elem in entry.findall("{http://arxiv.org/schemas/atom}primary_category"):
        term = cat_elem.get("term")
        if term:
            categories.append(term)
    for cat_elem in entry.findall(f"{ATOM_NS}category"):
        term = cat_elem.get("term")
        if term and term not in categories:
            categories.append(term)

    return ContentItem(
        source="arxiv",
        source_id=arxiv_id,
        title=title,
        url=arxiv_url,
        published_at=published_at,
        fetched_at=now_iso,
        author=", ".join(authors) if authors else None,
        description=description,
        content_type="paper",
        metadata={
            "authors": authors,
            "pdf_url": pdf_url,
            "categories": categories,
        },
    )


def _parse_arxiv_date(date_str: str) -> Optional[datetime]:
    """Parse an arXiv date string into a timezone-aware datetime."""
    # arXiv dates are typically ISO 8601: 2024-01-15T12:00:00Z
    try:
        # Handle 'Z' suffix
        cleaned = date_str.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        pass

    # Fallback patterns
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

    logger.warning("Could not parse arXiv date: %s", date_str)
    return None
