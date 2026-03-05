#!/usr/bin/env python3
"""Orithena Pulse — main pipeline orchestrator.

Entry point that orchestrates the full content intelligence pipeline:
    scrape -> deduplicate -> curate/score -> build site -> generate intelligence

Usage:
    python run.py                      # Full pipeline with default domain
    python run.py --domain agentic     # Explicit domain
    python run.py --scrape-only        # Only run scrapers
    python run.py --curate-only        # Only run curation (on cached raw data)
    python run.py --build-only         # Only build site (from cached scored data)
    python run.py --intel-only         # Only generate intelligence reports
    python run.py --demo               # Run with fixture data (no network calls)
"""

import argparse
import importlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from config import DATA_DIR, RAW_DIR, DOMAINS_DIR, FIXTURES_DIR, SITE_DIR, PROJECT_ROOT
from models import ContentItem, ScoredItem
from scraper import ADAPTERS
from curator.dedup import deduplicate
from curator.scorer import score_items
from intelligence.report import generate_report, save_report
from intelligence.digest import generate_digest
from intelligence.fit_evaluator import evaluate_fits

from sitegen.build import build_site

logger = logging.getLogger("pulse")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Orithena Pulse content intelligence pipeline",
    )
    parser.add_argument(
        "--domain",
        default="agentic",
        help="Domain config to load from domains/{DOMAIN}.yaml (default: agentic)",
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Only run scrapers, then exit",
    )
    parser.add_argument(
        "--curate-only",
        action="store_true",
        help="Only run curation on cached raw data, then exit",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Only build site from cached scored data, then exit",
    )
    parser.add_argument(
        "--intel-only",
        action="store_true",
        help="Only generate intelligence reports from cached scored data, then exit",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with fixture data instead of live scraping (no network calls)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Domain config
# ---------------------------------------------------------------------------

def load_domain_config(domain: str) -> dict:
    """Load and return a domain YAML configuration.

    Args:
        domain: Name of the domain (without extension). Looked up in
            ``domains/{domain}.yaml``.

    Returns:
        Parsed YAML dict.

    Raises:
        SystemExit: If the config file cannot be found or parsed.
    """
    config_path = DOMAINS_DIR / f"{domain}.yaml"
    if not config_path.exists():
        logger.error("Domain config not found: %s", config_path)
        sys.exit(1)
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        logger.error("Failed to parse domain config %s: %s", config_path, exc)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------

def stage_scrape(domain_config: dict) -> list[ContentItem]:
    """Stage 1: Scrape — run all enabled source adapters.

    Returns:
        Flat list of all ContentItems fetched across all sources.
    """
    logger.info("=== Stage 1: Scrape ===")
    all_items: list[ContentItem] = []
    sources = domain_config.get("sources", {})

    for source_name, source_config in sources.items():
        if not source_config.get("enabled", False):
            logger.info("Skipping disabled source: %s", source_name)
            continue

        adapter_key = source_config.get("adapter", source_name)
        adapter_cls = ADAPTERS.get(adapter_key)
        if adapter_cls is None:
            logger.warning(
                "No adapter registered for '%s' (source: %s), skipping",
                adapter_key,
                source_name,
            )
            continue

        try:
            adapter = adapter_cls(source_config)
            items = adapter.run()
            adapter.save_raw(items, source_name)
            all_items.extend(items)
            logger.info("Source %s: fetched %d items", source_name, len(items))
        except Exception:
            logger.exception("Error running adapter for source '%s'", source_name)

    logger.info("Scrape complete: %d total items", len(all_items))
    return all_items


def stage_deduplicate(items: list[ContentItem]) -> list[ContentItem]:
    """Stage 2: Deduplicate items across sources.

    Returns:
        Deduplicated list of ContentItems.
    """
    logger.info("=== Stage 2: Deduplicate ===")
    deduped = deduplicate(items)
    logger.info("Dedup: %d -> %d items", len(items), len(deduped))
    return deduped


def stage_curate(
    items: list[ContentItem], domain_config: dict
) -> list[ScoredItem]:
    """Stage 3: Score and curate items.

    Scores all items, filters to those passing the threshold, and persists
    the scored results to ``data/scored.json``.

    Returns:
        List of ScoredItems that passed the quality threshold.
    """
    logger.info("=== Stage 3: Score / Curate ===")
    scored = score_items(items, domain_config)

    # Persist full scored list (including below-threshold) for later stages
    scored_path = DATA_DIR / "scored.json"
    scored_path.write_text(
        json.dumps([s.to_dict() for s in scored], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved %d scored items to %s", len(scored), scored_path)

    passed = [s for s in scored if s.passed_threshold]
    logger.info(
        "Curation: %d scored, %d passed threshold", len(scored), len(passed)
    )
    return passed


def stage_fit_evaluation(
    scored_items: list[ScoredItem],
) -> list[ScoredItem]:
    """Stage 3.5: Evaluate Orithena fit for each item via LLM.

    Enriches each ScoredItem with fit data (why_unique, fit_score, etc.).
    Degrades gracefully if API is unavailable. Re-persists scored.json
    so that --build-only and --intel-only pick up the fit data.

    Returns:
        The same list with fit data attached.
    """
    logger.info("=== Stage 3.5: Fit Evaluation ===")
    fits = evaluate_fits(scored_items)
    for item in scored_items:
        slug = item.item.slug
        if slug in fits:
            item.fit = fits[slug]
    n_high = sum(1 for item in scored_items if item.high_signal)
    logger.info("Fit evaluation: %d items, %d high signal", len(scored_items), n_high)

    # Re-persist scored.json with fit data included
    scored_path = DATA_DIR / "scored.json"
    scored_path.write_text(
        json.dumps([s.to_dict() for s in scored_items], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Updated scored.json with fit data")

    return scored_items


def stage_build_site(
    scored_items: list[ScoredItem], domain_config: dict, date_str: str
) -> None:
    """Stage 4: Build the static site."""
    logger.info("=== Stage 4: Build Site ===")
    try:
        build_site(scored_items, domain_config, date_str)
        logger.info("Site built successfully: %s", SITE_DIR)
    except Exception:
        logger.exception("Error building site")


def stage_intelligence(
    scored_items: list[ScoredItem], domain_config: dict, date_str: str
) -> int:
    """Stage 5: Generate intelligence reports and digest.

    Returns:
        Number of individual reports generated.
    """
    logger.info("=== Stage 5: Intelligence ===")
    reports_generated = 0

    # Per-item reports
    for scored in scored_items:
        try:
            report = generate_report(scored, domain_config)
            save_report(report, date_str)
            reports_generated += 1
        except Exception:
            logger.exception(
                "Error generating report for '%s'", scored.item.title
            )

    logger.info("Generated %d individual reports", reports_generated)

    # Daily digest
    try:
        digest_text = generate_digest(scored_items, domain_config, date_str)

        # Save digest locally
        digest_path = DATA_DIR / f"digest-{date_str}.md"
        digest_path.write_text(digest_text, encoding="utf-8")
        logger.info("Saved digest to %s", digest_path)
    except Exception:
        logger.exception("Error generating digest")

    return reports_generated


# ---------------------------------------------------------------------------
# Cached-data loaders (for --*-only modes)
# ---------------------------------------------------------------------------

def load_cached_raw() -> list[ContentItem]:
    """Load all cached raw items from data/raw/**/*.json.

    Used by --curate-only to skip the scrape stage.
    """
    items: list[ContentItem] = []
    if not RAW_DIR.exists():
        logger.warning("Raw data directory does not exist: %s", RAW_DIR)
        return items

    for json_file in sorted(RAW_DIR.rglob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            for entry in data:
                items.append(ContentItem.from_dict(entry))
        except Exception:
            logger.exception("Error loading raw file: %s", json_file)

    logger.info("Loaded %d cached raw items from %s", len(items), RAW_DIR)
    return items


def load_cached_scored() -> list[ScoredItem]:
    """Load cached scored items from data/scored.json.

    Used by --build-only and --intel-only to skip scrape + curate stages.
    """
    scored_path = DATA_DIR / "scored.json"
    if not scored_path.exists():
        logger.warning("Scored data not found: %s", scored_path)
        return []

    try:
        data = json.loads(scored_path.read_text(encoding="utf-8"))
        scored = [ScoredItem.from_dict(entry) for entry in data]
        passed = [s for s in scored if s.passed_threshold]
        logger.info(
            "Loaded %d cached scored items (%d passed threshold)",
            len(scored),
            len(passed),
        )
        return passed
    except Exception:
        logger.exception("Error loading scored data: %s", scored_path)
        return []


def load_demo_items() -> list[ContentItem]:
    """Load fixture data for demo mode from fixtures/demo_items.json.

    Returns:
        List of ContentItems parsed from fixture data.

    Raises:
        SystemExit: If fixture file cannot be found or parsed.
    """
    fixture_path = FIXTURES_DIR / "demo_items.json"
    if not fixture_path.exists():
        logger.error("Demo fixture file not found: %s", fixture_path)
        sys.exit(1)

    try:
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        items = [ContentItem.from_dict(entry) for entry in data]
        logger.info("Loaded %d demo fixture items", len(items))
        return items
    except Exception:
        logger.exception("Error loading demo fixture: %s", fixture_path)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the Orithena Pulse pipeline."""
    # Logging
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )

    args = parse_args()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info("Orithena Pulse starting — domain=%s, date=%s", args.domain, date_str)

    # Load domain config (critical — exit on failure)
    domain_config = load_domain_config(args.domain)
    logger.info("Loaded domain config: %s", domain_config.get("name", args.domain))

    # Track summary counters
    n_scraped = 0
    n_deduped = 0
    n_passed = 0
    n_reports = 0

    # --scrape-only: scrape and exit
    if args.scrape_only:
        items = stage_scrape(domain_config)
        n_scraped = len(items)
        _print_summary(n_scraped, 0, 0, 0, date_str)
        return

    # --curate-only: load cached raw, dedup, score, exit
    if args.curate_only:
        raw_items = load_cached_raw()
        n_scraped = len(raw_items)
        deduped = stage_deduplicate(raw_items)
        n_deduped = len(deduped)
        passed = stage_curate(deduped, domain_config)
        n_passed = len(passed)
        _print_summary(n_scraped, n_deduped, n_passed, 0, date_str)
        return

    # --build-only: load cached scored, build site, exit
    if args.build_only:
        scored = load_cached_scored()
        n_passed = len(scored)
        stage_build_site(scored, domain_config, date_str)
        _print_summary(0, 0, n_passed, 0, date_str)
        return

    # --intel-only: load cached scored, generate intel, exit
    if args.intel_only:
        scored = load_cached_scored()
        n_passed = len(scored)
        n_reports = stage_intelligence(scored, domain_config, date_str)
        _print_summary(0, 0, n_passed, n_reports, date_str)
        return

    # --- Full pipeline ---

    # Stage 1: Scrape (or load demo fixtures)
    if args.demo:
        logger.info("Demo mode: using fixture data (no network calls)")
        print("Demo mode: using fixture data")
        all_items = load_demo_items()
    else:
        all_items = stage_scrape(domain_config)
    n_scraped = len(all_items)

    # Stage 2: Deduplicate
    deduped = stage_deduplicate(all_items)
    n_deduped = len(deduped)

    # Stage 3: Score / Curate
    passed = stage_curate(deduped, domain_config)
    n_passed = len(passed)

    # Stage 3.5: Fit Evaluation
    passed = stage_fit_evaluation(passed)

    # Stage 4: Build Site
    stage_build_site(passed, domain_config, date_str)

    # Stage 5: Intelligence
    n_reports = stage_intelligence(passed, domain_config, date_str)

    # Summary
    _print_summary(n_scraped, n_deduped, n_passed, n_reports, date_str)
    logger.info("Orithena Pulse pipeline complete")


def _print_summary(
    n_scraped: int,
    n_deduped: int,
    n_passed: int,
    n_reports: int,
    date_str: str,
) -> None:
    """Print a human-readable pipeline summary."""
    print()
    print("=" * 50)
    print("  Orithena Pulse — Pipeline Summary")
    print("=" * 50)
    print(f"  Date:             {date_str}")
    print(f"  Items scraped:    {n_scraped}")
    print(f"  After dedup:      {n_deduped}")
    print(f"  Passed curation:  {n_passed}")
    print(f"  Reports generated:{n_reports}")
    print(f"  Site output:      {SITE_DIR}")
    print("=" * 50)
    print()


if __name__ == "__main__":
    main()
