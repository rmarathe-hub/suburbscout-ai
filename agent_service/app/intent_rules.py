"""Strict user-intent inference — delegates to shared intent_classifier (Phase 1.3)."""

from __future__ import annotations

from app.intent_classifier import (
    ClassifiedIntent,
    classify_user_intent,
    route_intent_matches,
)

# Backward-compatible aliases
StrictIntent = ClassifiedIntent
StrictIntentKind = str


def infer_strict_intent(query: str) -> ClassifiedIntent:
    """Infer what the user actually asked for (strict, for validation/routing)."""
    return classify_user_intent(query)


def route_intent_matches_strict(route_intent: str, strict: ClassifiedIntent) -> bool:
    """True when router intent aligns with strict expected intent."""
    return route_intent_matches(strict, route_intent)
