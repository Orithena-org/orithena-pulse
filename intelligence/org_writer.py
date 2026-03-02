"""Org writer — stub.

Previously published intelligence to orithena-org. Now a no-op;
digest and reports stay in data/ within this repo.
"""

import logging

from models import ScoredItem

logger = logging.getLogger(__name__)


def write_to_org(
    digest_text: str,
    scored_items: list[ScoredItem],
    domain_config: dict,
    date_str: str,
) -> None:
    """No-op. Retained for interface compatibility."""
    logger.debug("org_writer is disabled — output stays in data/")
