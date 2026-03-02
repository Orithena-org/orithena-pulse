"""Data models for Orithena Pulse content intelligence pipeline."""

from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
import re


@dataclass
class ContentItem:
    """Raw item from any source adapter."""
    source: str              # "hn", "arxiv", "github_trending", "rss"
    source_id: str           # Unique ID within source (HN objectID, arxiv ID, etc.)
    title: str
    url: str                 # Canonical URL to the content
    published_at: str        # ISO 8601
    fetched_at: str          # ISO 8601
    author: Optional[str] = None
    description: Optional[str] = None  # Summary, abstract, or first paragraph
    content_type: str = "article"  # "article", "paper", "repo", "discussion", "launch"
    metadata: dict = field(default_factory=dict)
    # metadata holds source-specific fields:
    #   HN: points, num_comments
    #   arxiv: authors list, categories, pdf_url
    #   GitHub: stars, forks, language, topics
    #   RSS: feed_name, feed_url

    @property
    def normalized_url(self) -> str:
        """URL normalized for dedup (strip tracking params, trailing slashes, etc.)."""
        parsed = urlparse(self.url)

        # Normalize scheme: http -> https
        scheme = "https"

        # Strip www. prefix from hostname
        hostname = parsed.hostname or ""
        if hostname.startswith("www."):
            hostname = hostname[4:]

        # Preserve port if non-standard
        netloc = hostname
        if parsed.port and parsed.port not in (80, 443):
            netloc = f"{hostname}:{parsed.port}"

        # Strip utm_* and common tracking query params
        tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                           "utm_content", "ref", "source", "fbclid", "gclid"}
        query_params = parse_qs(parsed.query, keep_blank_values=False)
        filtered_params = {
            k: v for k, v in query_params.items()
            if k.lower() not in tracking_params and not k.lower().startswith("utm_")
        }
        # Sort params for consistent ordering
        query_string = urlencode(filtered_params, doseq=True) if filtered_params else ""

        # Strip trailing slashes from path
        path = parsed.path.rstrip("/")

        return urlunparse((scheme, netloc, path, "", query_string, ""))

    @property
    def slug(self) -> str:
        """Filesystem-safe slug derived from source + source_id."""
        return f"{self.source}__{self.source_id.replace('/', '_')}"

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON storage."""
        data = asdict(self)
        data["normalized_url"] = self.normalized_url
        data["slug"] = self.slug
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ContentItem":
        """Deserialize from a plain dict."""
        # Remove computed properties that aren't constructor args
        data = dict(data)
        data.pop("normalized_url", None)
        data.pop("slug", None)
        return cls(**data)


@dataclass
class ScoredItem:
    """Item after curation scoring."""
    item: ContentItem
    score: float             # 0.0-10.0 composite score
    scores: dict             # Breakdown: {"novelty": 7.5, "relevance": 8.0, ...}
    passed_threshold: bool   # Whether it meets minimum quality bar
    tags: list[str] = field(default_factory=list)  # Auto-assigned tags from domain

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON storage."""
        return {
            "item": self.item.to_dict(),
            "score": self.score,
            "scores": self.scores,
            "passed_threshold": self.passed_threshold,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScoredItem":
        """Deserialize from a plain dict."""
        return cls(
            item=ContentItem.from_dict(data["item"]),
            score=data["score"],
            scores=data["scores"],
            passed_threshold=data["passed_threshold"],
            tags=data.get("tags", []),
        )


@dataclass
class IntelReport:
    """Structured intelligence report for a single item."""
    item: ContentItem
    score: float
    what_it_is: str          # 2-3 sentence summary
    novel_aspects: str       # What's new vs existing approaches
    relevance: str           # Relevance to Orithena's interests
    recommended_action: str  # "adopt" | "watch" | "ignore" | "investigate"
    key_concepts: list[str]  # Extracted concepts/terms
    code_snippets: list[str] = field(default_factory=list)  # Key code if applicable
    links: list[str] = field(default_factory=list)  # Related links
    generated_at: str = ""   # ISO 8601

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON storage."""
        return {
            "item": self.item.to_dict(),
            "score": self.score,
            "what_it_is": self.what_it_is,
            "novel_aspects": self.novel_aspects,
            "relevance": self.relevance,
            "recommended_action": self.recommended_action,
            "key_concepts": self.key_concepts,
            "code_snippets": self.code_snippets,
            "links": self.links,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IntelReport":
        """Deserialize from a plain dict."""
        return cls(
            item=ContentItem.from_dict(data["item"]),
            score=data["score"],
            what_it_is=data["what_it_is"],
            novel_aspects=data["novel_aspects"],
            relevance=data["relevance"],
            recommended_action=data["recommended_action"],
            key_concepts=data["key_concepts"],
            code_snippets=data.get("code_snippets", []),
            links=data.get("links", []),
            generated_at=data.get("generated_at", ""),
        )
