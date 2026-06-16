"""Phase 8.5 — LLM-proposed commute intent with Python validation (regex fallback)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

from app.commute_destination import CommuteDestinationResult, detect_commute_destination_regex
from app.commute_service import (
    BOSTON_LABEL,
    commute_destination_label,
    dynamic_commute_available,
    resolve_dataset_town,
)
from app.town_normalizer import canonical_town_name

if TYPE_CHECKING:
    from app.query_plan import QueryPlan


class CommuteContext(StrEnum):
    DEFAULT_BOSTON = "default_boston"
    DESTINATION_TOWN = "destination_town"
    UNSUPPORTED = "unsupported"


class CommuteIntent(BaseModel):
    """Planner-emitted commute slots (validated by Python before execution)."""

    commute_destination_town: str | None = Field(
        default=None,
        description="Workplace/commute destination; canonical dataset town or unsupported label",
    )
    commute_origin_town: str | None = Field(
        default=None,
        description="Origin for point-to-point commute lookups",
    )
    compare_towns: list[str] = Field(
        default_factory=list,
        description="Towns being compared (not the commute destination)",
    )
    commute_context: CommuteContext = CommuteContext.DEFAULT_BOSTON
    max_commute_minutes: int | None = Field(
        default=None,
        description="When user states a drive-time cap, mirror it here and in rank preferences",
    )

    @field_validator(
        "commute_destination_town",
        "commute_origin_town",
        mode="before",
    )
    @classmethod
    def _strip_optional_town(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("compare_towns", mode="before")
    @classmethod
    def _strip_compare_towns(cls, value: Any) -> Any:
        if not value:
            return []
        if isinstance(value, list):
            return [t.strip() for t in value if isinstance(t, str) and t.strip()]
        return value

    @field_validator("commute_context", mode="before")
    @classmethod
    def _normalize_context(cls, value: Any) -> Any:
        if value is None:
            return CommuteContext.DEFAULT_BOSTON
        if isinstance(value, CommuteContext):
            return value
        text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        for ctx in CommuteContext:
            if text == ctx.value:
                return ctx
        return CommuteContext.DEFAULT_BOSTON


@dataclass(frozen=True)
class ResolvedCommuteIntent:
    """Validated commute intent used by normalizer, trust gates, and metadata."""

    commute_destination_town: str | None
    commute_origin_town: str | None
    compare_towns: tuple[str, ...]
    commute_context: CommuteContext
    label: str
    is_default: bool
    in_dataset: bool
    data_available: bool
    mention: str | None = None
    source: str = "default"

    def to_commute_intent(self) -> CommuteIntent:
        return CommuteIntent(
            commute_destination_town=self.commute_destination_town or self.mention,
            commute_origin_town=self.commute_origin_town,
            compare_towns=list(self.compare_towns),
            commute_context=self.commute_context,
        )

    def to_destination_result(self) -> CommuteDestinationResult:
        from app.commute_destination import DEFAULT_DESTINATION_KEY, normalize_destination_key

        if self.is_default:
            return CommuteDestinationResult(
                destination_town=None,
                label=BOSTON_LABEL,
                is_default=True,
                in_dataset=True,
                data_available=True,
                mention=None,
                key=DEFAULT_DESTINATION_KEY,
            )
        key = (
            normalize_destination_key(self.commute_destination_town)
            if self.commute_destination_town
            else "unknown_destination"
        )
        return CommuteDestinationResult(
            destination_town=self.commute_destination_town,
            label=self.label,
            is_default=False,
            in_dataset=self.in_dataset,
            data_available=self.data_available,
            mention=self.mention,
            key=key,
        )

    def compare_destination_town(self) -> str | None:
        if self.commute_context == CommuteContext.DESTINATION_TOWN and self.commute_destination_town:
            return self.commute_destination_town
        return None

    def has_non_default_destination(self) -> bool:
        return self.commute_context != CommuteContext.DEFAULT_BOSTON


def _canonical_dataset_town(name: str | None) -> str | None:
    if not name:
        return None
    resolved = resolve_dataset_town(name.strip())
    return canonical_town_name(resolved) if resolved else None


def _normalize_compare_towns(names: list[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        town = _canonical_dataset_town(raw)
        if not town:
            continue
        key = town.lower()
        if key not in seen:
            seen.add(key)
            out.append(town)
    return tuple(out)


def _resolved_from_destination_result(
    dest: CommuteDestinationResult,
    *,
    compare_towns: tuple[str, ...] = (),
    origin_town: str | None = None,
    source: str,
) -> ResolvedCommuteIntent:
    if dest.is_default:
        context = CommuteContext.DEFAULT_BOSTON
    elif dest.in_dataset:
        context = CommuteContext.DESTINATION_TOWN
    else:
        context = CommuteContext.UNSUPPORTED
    return ResolvedCommuteIntent(
        commute_destination_town=dest.destination_town,
        commute_origin_town=origin_town,
        compare_towns=compare_towns,
        commute_context=context,
        label=dest.label,
        is_default=dest.is_default,
        in_dataset=dest.in_dataset,
        data_available=dest.data_available,
        mention=dest.mention,
        source=source,
    )


def _resolve_llm_commute_intent(
    llm: CommuteIntent,
    *,
    compare_towns: tuple[str, ...] = (),
) -> ResolvedCommuteIntent:
    """Validate planner commute_intent in Python (no NL regex when intent exists)."""
    dest_town = _canonical_dataset_town(llm.commute_destination_town)
    origin_town = _canonical_dataset_town(llm.commute_origin_town)
    compare_towns = compare_towns or _normalize_compare_towns(list(llm.compare_towns))
    raw_dest = (llm.commute_destination_town or "").strip()

    if llm.commute_context == CommuteContext.DEFAULT_BOSTON and not raw_dest:
        return _default_boston_resolved(
            compare_towns=compare_towns,
            origin_town=origin_town,
            source="llm",
        )

    if raw_dest.lower() in _VAGUE_UNSUPPORTED_MENTIONS:
        return _default_boston_resolved(
            compare_towns=compare_towns,
            origin_town=origin_town,
            source="llm+default_cleanup",
        )

    if llm.commute_context == CommuteContext.UNSUPPORTED or (raw_dest and not dest_town):
        mention = raw_dest or None
        if not mention or mention.lower() in _VAGUE_UNSUPPORTED_MENTIONS:
            return _default_boston_resolved(
                compare_towns=compare_towns,
                origin_town=origin_town,
                source="llm+default_cleanup",
            )
        return ResolvedCommuteIntent(
            commute_destination_town=None,
            commute_origin_town=origin_town,
            compare_towns=compare_towns,
            commute_context=CommuteContext.UNSUPPORTED,
            label=mention or "unknown destination",
            is_default=False,
            in_dataset=False,
            data_available=False,
            mention=mention,
            source="llm",
        )

    if dest_town:
        return ResolvedCommuteIntent(
            commute_destination_town=dest_town,
            commute_origin_town=origin_town,
            compare_towns=compare_towns,
            commute_context=CommuteContext.DESTINATION_TOWN,
            label=commute_destination_label(dest_town),
            is_default=False,
            in_dataset=True,
            data_available=dynamic_commute_available(),
            mention=raw_dest or None,
            source="llm",
        )

    return _default_boston_resolved(
        compare_towns=compare_towns,
        origin_town=origin_town,
        source="llm",
    )


def _default_boston_resolved(
    *,
    compare_towns: tuple[str, ...] = (),
    origin_town: str | None = None,
    source: str,
) -> ResolvedCommuteIntent:
    return _resolved_from_destination_result(
        CommuteDestinationResult(
            destination_town=None,
            label=BOSTON_LABEL,
            is_default=True,
            in_dataset=True,
            data_available=True,
        ),
        compare_towns=compare_towns,
        origin_town=origin_town,
        source=source,
    )


def _merge_llm_and_regex(
    query: str,
    llm_intent: CommuteIntent | None,
    *,
    regex_fallback: bool = True,
) -> ResolvedCommuteIntent:
    if llm_intent is not None:
        return _resolve_llm_commute_intent(llm_intent)

    if not regex_fallback:
        return _default_boston_resolved(source="default")

    regex_dest = detect_commute_destination_regex(query)
    return _resolved_from_destination_result(regex_dest, source="regex")


_VAGUE_UNSUPPORTED_MENTIONS = frozenset(
    {"that place", "unknown", "unknown destination", "there", "somewhere"}
)


def resolve_commute_intent(
    query: str,
    llm_intent: CommuteIntent | None = None,
    *,
    plan: QueryPlan | None = None,
) -> ResolvedCommuteIntent:
    """
    Merge LLM commute_intent slots with regex fallback; validate against dataset.
    """
    from app.query_plan import CompareOp

    intent = (llm_intent or (plan.commute_intent if plan else None) or CommuteIntent()).model_copy(
        deep=True
    )

    if not intent.compare_towns and plan:
        for op in plan.ops:
            if isinstance(op, CompareOp) and len(op.towns) >= 2:
                intent.compare_towns = list(op.towns[:2])
                break

    has_llm_intent = llm_intent is not None or (plan and plan.commute_intent is not None)
    resolved = _merge_llm_and_regex(
        query,
        intent if has_llm_intent else None,
        regex_fallback=not has_llm_intent,
    )

    if not resolved.compare_towns and plan:
        for op in plan.ops:
            if isinstance(op, CompareOp):
                resolved = ResolvedCommuteIntent(
                    commute_destination_town=resolved.commute_destination_town,
                    commute_origin_town=resolved.commute_origin_town,
                    compare_towns=_normalize_compare_towns(op.towns),
                    commute_context=resolved.commute_context,
                    label=resolved.label,
                    is_default=resolved.is_default,
                    in_dataset=resolved.in_dataset,
                    data_available=resolved.data_available,
                    mention=resolved.mention,
                    source=resolved.source,
                )
                break

    return resolved


def apply_commute_intent_to_plan(query: str, plan: QueryPlan) -> QueryPlan:
    """Normalize plan ops using validated commute intent."""
    from app.query_plan import CompareOp, QueryPlan, RankOp, validate_plan

    resolved = resolve_commute_intent(query, plan.commute_intent, plan=plan)
    new_ops: list[Any] = []

    for op in plan.ops:
        if isinstance(op, CompareOp):
            dest = resolved.compare_destination_town()
            new_ops.append(
                CompareOp(
                    towns=op.towns,
                    columns=op.columns,
                    commute_destination_town=dest or op.commute_destination_town,
                )
            )
        elif isinstance(op, RankOp):
            from app.plan_preferences import merge_rank_preferences

            prefs = merge_rank_preferences(
                query,
                op.preferences,
                commute_intent=resolved.to_commute_intent(),
                regex_fallback=False,
            )
            if resolved.commute_context == CommuteContext.DESTINATION_TOWN and resolved.commute_destination_town:
                prefs = prefs.model_copy(
                    update={"commute_destination_town": resolved.commute_destination_town}
                )
            new_ops.append(
                RankOp(
                    preferences=prefs,
                    limit=op.limit,
                    use_semantic_candidates=op.use_semantic_candidates,
                )
            )
        else:
            new_ops.append(op)

    final_commute = resolved.to_commute_intent()
    if plan.commute_intent and plan.commute_intent.max_commute_minutes is not None:
        final_commute = final_commute.model_copy(
            update={"max_commute_minutes": plan.commute_intent.max_commute_minutes}
        )

    return validate_plan(
        QueryPlan(
            ops=new_ops,
            user_intent_summary=plan.user_intent_summary,
            commute_intent=final_commute,
        )
    )
