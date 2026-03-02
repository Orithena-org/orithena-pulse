"""Base adapter for all content scrapers."""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import REQUEST_TIMEOUT, USER_AGENT, RAW_DIR
from models import ContentItem

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """Abstract base class for all scraper adapters.

    Each adapter is responsible for fetching content from a single source
    and returning a list of ContentItem objects.
    """

    def __init__(self, domain_config: dict) -> None:
        self.config = domain_config
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Set default headers
        self.session.headers.update({"User-Agent": USER_AGENT})

    @abstractmethod
    def fetch(self) -> list[ContentItem]:
        """Fetch content items from the source.

        Returns:
            List of ContentItem objects fetched from the source.
        """
        ...

    def run(self) -> list[ContentItem]:
        """Execute the adapter with error handling.

        Calls fetch() and handles any exceptions, logging failures.

        Returns:
            List of ContentItem objects, or empty list on failure.
        """
        adapter_name = getattr(self, "name", self.__class__.__name__)
        logger.info("Running adapter: %s", adapter_name)
        try:
            items = self.fetch()
            logger.info(
                "Adapter %s fetched %d items", adapter_name, len(items)
            )
            return items
        except requests.RequestException as exc:
            logger.error(
                "Network error in adapter %s: %s", adapter_name, exc
            )
            return []
        except Exception:
            logger.exception("Unexpected error in adapter %s", adapter_name)
            return []

    def save_raw(self, items: list[ContentItem], source_name: str) -> None:
        """Save raw fetched items to disk for archival/debugging.

        Writes items to RAW_DIR/{source_name}/{date}.json.

        Args:
            items: List of ContentItem objects to save.
            source_name: Name of the source (used as subdirectory).
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        output_dir = Path(RAW_DIR) / source_name
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{today}.json"

        serialized = []
        for item in items:
            entry = {
                "source": item.source,
                "source_id": item.source_id,
                "title": item.title,
                "url": item.url,
                "published_at": item.published_at,
                "fetched_at": item.fetched_at,
                "author": item.author,
                "description": item.description,
                "content_type": item.content_type,
                "metadata": item.metadata,
            }
            serialized.append(entry)

        output_path.write_text(
            json.dumps(serialized, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(
            "Saved %d raw items to %s", len(serialized), output_path
        )
