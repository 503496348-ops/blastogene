"""Safety checks for community-operation message rewrites."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RewriteDecision:
    accepted: bool
    reasons: tuple[str, ...]


def evaluate_rewrite(source: str, candidate: str, protected_terms: Iterable[str]) -> RewriteDecision:
    reasons: list[str] = []
    if not candidate.strip():
        reasons.append("empty candidate")
    for term in protected_terms:
        if term and term in source and term not in candidate:
            reasons.append(f"dropped protected term: {term}")
    if "http" in source and "http" not in candidate:
        reasons.append("dropped link")
    if len(candidate) > max(240, len(source) * 2):
        reasons.append("candidate too verbose")
    return RewriteDecision(not reasons, tuple(reasons))


def compact_for_alert(text: str, limit: int = 120) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "…"
