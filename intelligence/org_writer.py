"""Org writer — publishes intelligence to orithena-org for agent consumption.

Writes the daily digest and individual reports to the shared org repository
so that agent-01 can read them at run start.

Target structure in orithena-org:
    intel/pulse/digest.md              <- overwritten daily
    intel/pulse/archive/{date}.md      <- archived copy per day
    intel/pulse/reports/{date}/*.md    <- per-item reports (score >= 6.0)
"""

import logging
import shutil
from pathlib import Path

from config import ORG_ROOT, REPORTS_DIR
from models import ScoredItem

logger = logging.getLogger(__name__)

# Minimum score for a report to be copied to org
ORG_REPORT_SCORE_THRESHOLD = 6.0


def _ensure_org_dirs(date_str: str) -> dict[str, Path]:
    """Create the org intel directory structure if it does not exist.

    Args:
        date_str: Date string (YYYY-MM-DD) for date-specific directories.

    Returns:
        Dict mapping directory role to its Path.
    """
    pulse_dir = ORG_ROOT / "intel" / "pulse"
    archive_dir = pulse_dir / "archive"
    reports_dir = pulse_dir / "reports" / date_str

    for d in (pulse_dir, archive_dir, reports_dir):
        d.mkdir(parents=True, exist_ok=True)

    return {
        "pulse": pulse_dir,
        "archive": archive_dir,
        "reports": reports_dir,
    }


def _write_digest(
    digest_text: str, dirs: dict[str, Path], date_str: str
) -> None:
    """Write the digest to both the rolling location and archive.

    Args:
        digest_text: The full markdown digest content.
        dirs: Directory paths from _ensure_org_dirs.
        date_str: Date string (YYYY-MM-DD) for the archive filename.
    """
    # Rolling digest (overwritten daily)
    digest_path = dirs["pulse"] / "digest.md"
    digest_path.write_text(digest_text, encoding="utf-8")
    logger.info("Wrote rolling digest: %s", digest_path)

    # Archive copy
    archive_path = dirs["archive"] / f"{date_str}.md"
    archive_path.write_text(digest_text, encoding="utf-8")
    logger.info("Wrote archive digest: %s", archive_path)


def _copy_reports(
    scored_items: list[ScoredItem],
    dirs: dict[str, Path],
    date_str: str,
) -> int:
    """Copy individual reports for high-scoring items to the org directory.

    Only copies reports for items with score >= ORG_REPORT_SCORE_THRESHOLD.
    The source reports are expected to exist in REPORTS_DIR/{date}/{slug}.md,
    written earlier by report.save_report().

    Args:
        scored_items: All scored items from the pipeline run.
        dirs: Directory paths from _ensure_org_dirs.
        date_str: Date string (YYYY-MM-DD) matching the reports subdirectory.

    Returns:
        Number of reports successfully copied.
    """
    source_dir = REPORTS_DIR / date_str
    if not source_dir.exists():
        logger.warning(
            "Reports source directory does not exist: %s", source_dir
        )
        return 0

    copied = 0
    for scored in scored_items:
        if scored.score < ORG_REPORT_SCORE_THRESHOLD:
            continue

        slug = scored.item.slug
        source_path = source_dir / f"{slug}.md"
        if not source_path.exists():
            logger.debug(
                "Report file not found for %s (score %.1f), skipping",
                slug,
                scored.score,
            )
            continue

        dest_path = dirs["reports"] / f"{slug}.md"
        shutil.copy2(source_path, dest_path)
        copied += 1
        logger.debug("Copied report to org: %s", dest_path)

    return copied


def write_to_org(
    digest_text: str,
    scored_items: list[ScoredItem],
    domain_config: dict,
    date_str: str,
) -> None:
    """Write intelligence output to orithena-org for agent consumption.

    Creates the required directory structure, writes the daily digest
    (both rolling and archived), and copies individual reports for
    items scoring 6.0+.

    Handles a missing ORG_ROOT gracefully by logging a warning and
    returning without error.

    Args:
        digest_text: The full markdown digest content.
        scored_items: All scored items from the pipeline run.
        domain_config: The full domain configuration dict (reserved for
            future use, e.g. domain-specific org paths).
        date_str: Date string (YYYY-MM-DD) for directory and file naming.
    """
    if not ORG_ROOT.exists():
        logger.warning(
            "ORG_ROOT does not exist (%s). Skipping org write. "
            "Set the ORG_ROOT env var or ensure orithena-org is checked out.",
            ORG_ROOT,
        )
        return

    logger.info("Writing intelligence to org: %s", ORG_ROOT)

    # Create directory structure
    dirs = _ensure_org_dirs(date_str)

    # Write digest (rolling + archive)
    _write_digest(digest_text, dirs, date_str)

    # Copy individual reports for high-scoring items
    n_qualifying = len(
        [s for s in scored_items if s.score >= ORG_REPORT_SCORE_THRESHOLD]
    )
    copied = _copy_reports(scored_items, dirs, date_str)
    logger.info(
        "Org write complete: digest written, %d/%d qualifying reports copied",
        copied,
        n_qualifying,
    )
