"""LLM-assisted rescoring (Phase 1.5 — not yet implemented)."""

from models import ScoredItem


def llm_rescore(items: list[ScoredItem], domain_config: dict) -> list[ScoredItem]:
    """Re-score top items using LLM analysis. Phase 1.5 feature — returns items unchanged."""
    return items
