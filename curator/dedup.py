"""Cross-source deduplication for Pulse content items."""

import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from typing import Optional

from models import ContentItem


# Query parameters to strip during URL normalization
_STRIP_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source"}

# Regex to extract arxiv paper IDs (e.g., 2403.12345 or 2403.12345v2)
_ARXIV_ID_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*)(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)


def _normalize_url(url: str) -> str:
    """Normalize a URL for deduplication comparison.

    - Upgrade http to https
    - Strip www. prefix from host
    - Remove tracking query params (utm_*, ref, source)
    - Strip trailing slashes from path
    """
    parsed = urlparse(url)

    # http -> https
    scheme = "https"

    # Strip www.
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Strip trailing slashes from path
    path = parsed.path.rstrip("/")

    # Filter query params
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in params.items() if k.lower() not in _STRIP_PARAMS}
        query = urlencode(filtered, doseq=True)
    else:
        query = ""

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


def _title_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity on word sets of two titles.

    Returns a float in [0, 1]. Titles are lowercased and split on whitespace.
    """
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _extract_arxiv_id(url: str) -> Optional[str]:
    """Extract an arxiv paper ID from a URL.

    Handles URLs like:
        https://arxiv.org/abs/2403.12345
        https://arxiv.org/pdf/2403.12345v2
    Returns the ID string (e.g., '2403.12345') or None.
    """
    match = _ARXIV_ID_RE.search(url)
    if match:
        paper_id = match.group(1)
        # Strip version suffix for canonical matching
        return re.sub(r"v\d+$", "", paper_id)
    return None


def _description_length(item: ContentItem) -> int:
    """Return the length of an item's description, or 0 if None."""
    return len(item.description) if item.description else 0


def _merge_items(keep: ContentItem, discard: ContentItem) -> ContentItem:
    """Merge two ContentItems, preferring the richer one.

    - Keep the longer description
    - Merge metadata dicts (keep's values win on conflict)
    - Track merged sources in metadata["merged_from"]
    """
    # Use the longer description
    if _description_length(discard) > _description_length(keep):
        keep.description = discard.description

    # Merge metadata (keep wins on key conflicts)
    merged_meta = {**discard.metadata, **keep.metadata}

    # Track provenance
    existing_merged = merged_meta.get("merged_from", [])
    if not isinstance(existing_merged, list):
        existing_merged = []
    existing_merged.append(discard.source)
    merged_meta["merged_from"] = existing_merged

    keep.metadata = merged_meta
    return keep


def deduplicate(items: list[ContentItem]) -> list[ContentItem]:
    """Deduplicate a list of ContentItems using three strategies.

    1. Exact URL match (after normalization) — keep the item with the most metadata.
    2. Title similarity (Jaccard >= 0.75 on word sets) — merge items from the same day.
    3. arxiv ID extraction — if an HN/RSS post links to an arxiv paper, merge
       (prefer arxiv metadata, keep HN engagement data).

    Returns a new list with duplicates removed/merged.
    """
    if not items:
        return []

    # --- Pass 1: Exact URL dedup ---
    url_groups: dict[str, list[ContentItem]] = {}
    for item in items:
        norm = item.normalized_url
        url_groups.setdefault(norm, []).append(item)

    deduped: list[ContentItem] = []
    for group in url_groups.values():
        # Sort by description length descending — richest item first
        group.sort(key=_description_length, reverse=True)
        best = group[0]
        for other in group[1:]:
            best = _merge_items(best, other)
        deduped.append(best)

    # --- Pass 2: arxiv ID merge ---
    arxiv_map: dict[str, ContentItem] = {}  # arxiv_id -> best item
    non_arxiv: list[ContentItem] = []

    for item in deduped:
        arxiv_id = _extract_arxiv_id(item.url)
        if arxiv_id is None:
            # Also check metadata for arxiv links (e.g., HN posts linking to arxiv)
            story_url = item.metadata.get("url", "")
            if story_url:
                arxiv_id = _extract_arxiv_id(story_url)

        if arxiv_id is not None:
            if arxiv_id in arxiv_map:
                existing = arxiv_map[arxiv_id]
                # Prefer arxiv source for metadata, but keep HN engagement
                if item.source == "arxiv":
                    merged = _merge_items(item, existing)
                elif existing.source == "arxiv":
                    merged = _merge_items(existing, item)
                else:
                    merged = _merge_items(existing, item)
                arxiv_map[arxiv_id] = merged
            else:
                arxiv_map[arxiv_id] = item
        else:
            non_arxiv.append(item)

    deduped = non_arxiv + list(arxiv_map.values())

    # --- Pass 3: Title similarity merge (same-day only) ---
    result: list[ContentItem] = []
    used = set()

    for i, item_a in enumerate(deduped):
        if i in used:
            continue
        for j in range(i + 1, len(deduped)):
            if j in used:
                continue
            item_b = deduped[j]

            # Same-day check: compare date portion of published_at
            day_a = item_a.published_at[:10] if item_a.published_at else ""
            day_b = item_b.published_at[:10] if item_b.published_at else ""
            if day_a != day_b:
                continue

            if _title_similarity(item_a.title, item_b.title) >= 0.75:
                item_a = _merge_items(item_a, item_b)
                used.add(j)

        result.append(item_a)

    return result
