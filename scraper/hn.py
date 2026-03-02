"""Hacker News adapter using the Algolia search API."""

import logging
import time
from datetime import datetime, timezone, timedelta

from config import REQUEST_TIMEOUT
from models import ContentItem
from scraper.base import BaseAdapter

logger = logging.getLogger(__name__)

HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={}"


class HNAdapter(BaseAdapter):
    """Fetches stories from Hacker News via the Algolia API."""

    name = "hn"

    def fetch(self) -> list[ContentItem]:
        queries = self.config["queries"]
        min_points = self.config.get("min_points", 5)
        max_age_hours = self.config.get("max_age_hours", 24)

        cutoff_ts = int(
            (datetime.now(timezone.utc) - timedelta(hours=max_age_hours))
            .timestamp()
        )
        now_iso = datetime.now(timezone.utc).isoformat()

        seen_ids: set[str] = set()
        items: list[ContentItem] = []

        for i, query in enumerate(queries):
            if i > 0:
                time.sleep(1)  # Rate limit: 1 second between requests

            params = {
                "query": query,
                "tags": "story",
                "numericFilters": (
                    f"points>={min_points},created_at_i>={cutoff_ts}"
                ),
            }

            logger.debug("HN query: %s params=%s", query, params)

            try:
                resp = self.session.get(
                    HN_ALGOLIA_URL, params=params, timeout=REQUEST_TIMEOUT
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                logger.exception("Failed to fetch HN query: %s", query)
                continue

            hits = data.get("hits", [])
            logger.debug("HN query '%s' returned %d hits", query, len(hits))

            for hit in hits:
                object_id = hit.get("objectID", "")
                if not object_id or object_id in seen_ids:
                    continue
                seen_ids.add(object_id)

                title = hit.get("title") or ""
                if not title:
                    continue

                # Prefer the story URL; fall back to HN discussion URL
                url = hit.get("url") or HN_ITEM_URL.format(object_id)

                # Parse published date
                created_at_i = hit.get("created_at_i")
                if created_at_i:
                    published_at = (
                        datetime.fromtimestamp(
                            created_at_i, tz=timezone.utc
                        ).isoformat()
                    )
                else:
                    published_at = hit.get("created_at", now_iso)

                points = hit.get("points", 0) or 0
                num_comments = hit.get("num_comments", 0) or 0
                author = hit.get("author")

                content_type = _classify_hn_item(title, num_comments, points)

                item = ContentItem(
                    source="hn",
                    source_id=object_id,
                    title=title,
                    url=url,
                    published_at=published_at,
                    fetched_at=now_iso,
                    author=author,
                    description=None,
                    content_type=content_type,
                    metadata={
                        "points": points,
                        "num_comments": num_comments,
                        "hn_url": HN_ITEM_URL.format(object_id),
                    },
                )
                items.append(item)

        logger.info("HN adapter collected %d unique items", len(items))
        return items


def _classify_hn_item(title: str, num_comments: int, points: int) -> str:
    """Classify an HN item by its content type.

    Returns:
        "launch" for Show HN / Launch HN posts,
        "discussion" for comment-heavy threads,
        "article" otherwise.
    """
    title_lower = title.strip().lower()
    if title_lower.startswith("show hn:") or title_lower.startswith("launch hn:"):
        return "launch"
    # If comments substantially outnumber points, it's discussion-heavy
    if num_comments > 0 and points > 0 and num_comments > points * 1.5:
        return "discussion"
    return "article"
