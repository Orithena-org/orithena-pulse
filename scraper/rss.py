"""RSS/Atom feed adapter using feedparser."""

import logging
import time
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from typing import Optional

import feedparser

from models import ContentItem
from scraper.base import BaseAdapter

logger = logging.getLogger(__name__)


class RSSAdapter(BaseAdapter):
    """Fetches articles from a list of RSS/Atom feeds."""

    name = "rss"

    def fetch(self) -> list[ContentItem]:
        feeds = self.config["feeds"]
        max_age_hours = self.config.get("max_age_hours", 48)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        now_iso = datetime.now(timezone.utc).isoformat()

        items: list[ContentItem] = []

        for i, feed_cfg in enumerate(feeds):
            feed_name = feed_cfg.get("name", "unknown")
            feed_url = feed_cfg.get("url", "")

            if not feed_url:
                logger.warning("RSS feed '%s' has no URL, skipping", feed_name)
                continue

            if i > 0:
                time.sleep(0.5)  # Brief pause between feed fetches

            logger.debug("Fetching RSS feed: %s (%s)", feed_name, feed_url)

            try:
                parsed = feedparser.parse(feed_url)
            except Exception:
                logger.exception(
                    "Failed to parse RSS feed: %s (%s)", feed_name, feed_url
                )
                continue

            if parsed.bozo and not parsed.entries:
                logger.warning(
                    "RSS feed '%s' had parse errors and no entries: %s",
                    feed_name,
                    parsed.bozo_exception,
                )
                continue

            for entry in parsed.entries:
                try:
                    item = _parse_entry(
                        entry, feed_name, feed_url, cutoff, now_iso
                    )
                    if item is not None:
                        items.append(item)
                except Exception:
                    logger.exception(
                        "Failed to parse RSS entry from feed '%s'", feed_name
                    )
                    continue

        logger.info("RSS adapter collected %d items", len(items))
        return items


def _parse_entry(
    entry,
    feed_name: str,
    feed_url: str,
    cutoff: datetime,
    now_iso: str,
) -> Optional[ContentItem]:
    """Parse a single feedparser entry into a ContentItem.

    Returns None if the entry is too old or missing required fields.
    """
    title = entry.get("title", "").strip()
    link = entry.get("link", "").strip()

    if not title or not link:
        return None

    # Parse published date
    published_dt = _parse_entry_date(entry)
    if published_dt is not None and published_dt < cutoff:
        return None
    published_at = published_dt.isoformat() if published_dt else now_iso

    # Prefer full content over summary
    description = _extract_content(entry)

    # Author
    author = entry.get("author") or entry.get("dc_creator") or None
    if author:
        author = author.strip()

    # Generate a stable source ID from the entry
    entry_id = entry.get("id") or entry.get("guid") or link
    source_id = sha256(entry_id.encode("utf-8")).hexdigest()[:16]

    return ContentItem(
        source="rss",
        source_id=source_id,
        title=title,
        url=link,
        published_at=published_at,
        fetched_at=now_iso,
        author=author,
        description=description,
        content_type="article",
        metadata={
            "feed_name": feed_name,
            "feed_url": feed_url,
        },
    )


def _extract_content(entry) -> Optional[str]:
    """Extract the best available content/summary from a feed entry.

    Prefers full content, falls back to summary.
    """
    # feedparser stores content as a list of dicts with 'value' keys
    content_list = entry.get("content")
    if content_list and isinstance(content_list, list):
        for content_item in content_list:
            value = content_item.get("value", "").strip()
            if value:
                return value

    # Fall back to summary
    summary = entry.get("summary", "").strip()
    if summary:
        return summary

    return None


def _parse_entry_date(entry) -> Optional[datetime]:
    """Parse the published date from a feed entry.

    feedparser normalizes dates into a time.struct_time in
    'published_parsed' or 'updated_parsed'.
    """
    # Try feedparser's pre-parsed date fields
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed_time = entry.get(field)
        if parsed_time:
            try:
                from calendar import timegm

                ts = timegm(parsed_time)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue

    # Try raw date strings
    for field in ("published", "updated", "created"):
        raw = entry.get(field, "").strip()
        if not raw:
            continue

        # ISO 8601
        try:
            cleaned = raw.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned)
        except (ValueError, TypeError):
            pass

        # RFC 2822 style (common in RSS)
        try:
            from email.utils import parsedate_to_datetime

            return parsedate_to_datetime(raw)
        except (ValueError, TypeError):
            continue

    return None
