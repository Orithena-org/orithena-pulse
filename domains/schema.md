# Domain YAML Schema

Each domain is defined by a single YAML file in the `domains/` directory. The domain config controls every aspect of the pipeline: which sources to scrape, how to score items, what focus areas to analyze, and how to render the site.

To create a new domain, copy `agentic.yaml` and modify it. No code changes required.

## Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable domain name (e.g., "Agentic AI") |
| `slug` | string | URL/filesystem-safe identifier (e.g., "agentic"). Must match the filename. |
| `description` | string | One-line description of what this domain covers. |

## `sources` Section

Defines which content sources to scrape. Each key is a source name with its adapter config.

### Common fields for all sources

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Whether to scrape this source. Set `false` to skip. |
| `adapter` | string | Which scraper adapter to use. Must match a key in `scraper.ADAPTERS`. |
| `max_age_hours` | int | Only fetch items published within this many hours. |

### Source: `hn` (Hacker News via Algolia)

| Field | Type | Description |
|-------|------|-------------|
| `queries` | list[str] | Search terms to query against HN. Each generates a separate API call. |
| `min_points` | int | Minimum HN points to include an item. |
| `include_show_hn` | bool | Also search for "Show HN" posts matching queries. |

### Source: `arxiv`

| Field | Type | Description |
|-------|------|-------------|
| `categories` | list[str] | arxiv category codes (e.g., "cs.AI", "cs.MA"). |
| `search_terms` | list[str] | Keywords to search within those categories. |
| `max_results` | int | Maximum papers to fetch per query. |

### Source: `github_trending`

| Field | Type | Description |
|-------|------|-------------|
| `topics` | list[str] | GitHub topics to filter trending repos (e.g., "ai-agent"). |
| `languages` | list[str] | Programming languages to filter. Empty list means all languages. |
| `min_stars` | int | Minimum star count to include. |

### Source: `rss`

| Field | Type | Description |
|-------|------|-------------|
| `feeds` | list[dict] | List of RSS/Atom feeds. Each has `name` (str) and `url` (str). |

## `scoring` Section

Controls how items are scored and filtered.

| Field | Type | Description |
|-------|------|-------------|
| `weights` | dict[str, float] | Weight for each scoring dimension. Keys: `novelty`, `relevance`, `signal_quality`, `engagement`. Should sum to ~1.0. |
| `threshold` | float | Minimum composite score (0-10) to pass curation. Items below this are discarded. |
| `high_signal_keywords` | list[str] | Keywords that boost relevance score when found in title/description. |
| `noise_keywords` | list[str] | Keywords that reduce relevance score (spam/noise indicators). |
| `source_trust` | dict[str, float] | Per-source quality multiplier applied to signal_quality score. Default 1.0. |

## `analysis` Section

Defines focus areas for relevance scoring and intelligence report generation.

| Field | Type | Description |
|-------|------|-------------|
| `focus_areas` | list[dict] | Each has `area` (name), `description` (what it covers), `keywords` (list of matching terms). |
| `analysis_prompt` | string | Jinja-style prompt template for LLM-assisted analysis (Phase 1.5+). Uses `{title}`, `{source}`, `{description}`, `{url}` placeholders. |

## `site` Section

Controls the public-facing static site output.

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Page title for the site. |
| `tagline` | string | Subtitle shown below the title. |
| `items_per_digest` | int | Maximum total items per daily digest page. |
| `show_scores` | bool | Whether to display numeric scores publicly. |
| `sections` | list[dict] | How to group items. Each has `name`, optional `description`, optional `filter` (dict with `content_type`), and `count`. |

## Adding a New Domain

1. Copy `agentic.yaml` to `domains/{slug}.yaml`
2. Change `name`, `slug`, `description`
3. Update `sources` -- change queries, feed URLs, topic filters
4. Update `scoring` -- adjust weights, keywords, threshold
5. Update `analysis.focus_areas` -- define what matters for this domain
6. Update `site` -- title, tagline, sections
7. Run: `python run.py --domain {slug}`

No code changes required.
