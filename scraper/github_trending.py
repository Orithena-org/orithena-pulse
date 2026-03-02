"""GitHub trending repositories adapter using the GitHub search API."""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import REQUEST_TIMEOUT
from models import ContentItem
from scraper.base import BaseAdapter

logger = logging.getLogger(__name__)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


class GitHubTrendingAdapter(BaseAdapter):
    """Fetches trending repositories from GitHub via the search API."""

    name = "github_trending"

    def fetch(self) -> list[ContentItem]:
        topics = self.config["topics"]
        min_stars = self.config.get("min_stars", 10)
        max_age_hours = self.config.get("max_age_hours", 48)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        now_iso = datetime.now(timezone.utc).isoformat()

        seen_names: set[str] = set()
        items: list[ContentItem] = []

        for i, topic in enumerate(topics):
            if i > 0:
                time.sleep(2)  # Rate limit: 2 seconds between requests

            query = f"topic:{topic} stars:>{min_stars} pushed:>{cutoff_str}"
            params = {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": 100,
            }

            logger.debug("GitHub search: topic=%s query=%s", topic, query)

            try:
                resp = self.session.get(
                    GITHUB_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                logger.exception(
                    "Failed to fetch GitHub trending for topic: %s", topic
                )
                continue

            repos = data.get("items", [])
            logger.debug(
                "GitHub topic '%s' returned %d repos", topic, len(repos)
            )

            for repo in repos:
                full_name = repo.get("full_name", "")
                if not full_name or full_name in seen_names:
                    continue
                seen_names.add(full_name)

                html_url = repo.get("html_url", "")
                if not html_url:
                    continue

                description = repo.get("description") or None
                stars = repo.get("stargazers_count", 0) or 0
                language = repo.get("language") or None
                repo_topics = repo.get("topics", []) or []

                # Parse published date (repo creation or last push)
                pushed_at = repo.get("pushed_at") or repo.get("created_at")
                published_at = _parse_github_date(pushed_at) or now_iso

                owner = repo.get("owner", {})
                author = owner.get("login") if owner else None

                item = ContentItem(
                    source="github_trending",
                    source_id=full_name,
                    title=full_name,
                    url=html_url,
                    published_at=published_at,
                    fetched_at=now_iso,
                    author=author,
                    description=description,
                    content_type="repo",
                    metadata={
                        "stars": stars,
                        "language": language,
                        "topics": repo_topics,
                        "forks": repo.get("forks_count", 0),
                        "open_issues": repo.get("open_issues_count", 0),
                    },
                )
                items.append(item)

        logger.info(
            "GitHub trending adapter collected %d unique repos", len(items)
        )
        return items


def _parse_github_date(date_str: Optional[str]) -> Optional[str]:
    """Parse a GitHub API date string into an ISO 8601 string.

    GitHub dates are typically in the format: 2024-01-15T12:00:00Z
    """
    if not date_str:
        return None

    try:
        cleaned = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.isoformat()
    except (ValueError, TypeError):
        pass

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        logger.warning("Could not parse GitHub date: %s", date_str)
        return None
