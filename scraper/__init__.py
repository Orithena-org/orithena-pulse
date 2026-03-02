"""Pulse content scrapers."""
from scraper.hn import HNAdapter
from scraper.arxiv import ArxivAdapter
from scraper.github_trending import GitHubTrendingAdapter
from scraper.rss import RSSAdapter

ADAPTERS = {
    "hn": HNAdapter,
    "arxiv": ArxivAdapter,
    "github_trending": GitHubTrendingAdapter,
    "rss": RSSAdapter,
}
