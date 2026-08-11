import json
from typing import Any

from src.schemas.mentions import DetailedMention, Mention
from src.schemas.query_generation import LinkedMention, LinkedMentions


def mentions_to_text(mentions: list[Any]) -> str:
    if not mentions:
        return "No mentions yet."

    lines: list[str] = []
    for index, mention in enumerate(mentions, start=1):
        lines.append(
            f"{index}. text={mention.text}, type={mention.type}, "
            f"label_pred={mention.label_pred}, attrs={mention.attrs or {}}"
        )
    return "\n".join(lines)


def _mention_key(mention: DetailedMention | Mention) -> tuple[str, str, str, str]:
    attrs = mention.attrs or {}
    attrs_key = json.dumps(attrs, sort_keys=True, ensure_ascii=False)
    return (mention.text, mention.type, mention.label_pred, attrs_key)


def to_detailed_mentions(mentions: list[Mention]) -> list[DetailedMention]:
    return [
        DetailedMention(
            text=mention.text,
            type=mention.type,
            label_pred=mention.label_pred,
            attrs=mention.attrs,
            selected_candidate_iri=mention.selected_candidate_iri,
            candidates=[],
        )
        for mention in mentions
    ]


def merge_mentions_with_existing_candidates(
    *,
    existing_mentions: list[DetailedMention],
    revised_mentions: list[DetailedMention],
) -> tuple[list[DetailedMention], int, int]:
    existing_by_key: dict[tuple[str, str, str, str], list[DetailedMention]] = {}
    for mention in existing_mentions:
        existing_by_key.setdefault(_mention_key(mention), []).append(mention)

    merged: list[DetailedMention] = []
    reused_count = 0
    changed_count = 0

    for revised in revised_mentions:
        key = _mention_key(revised)
        matched_existing = None
        if key in existing_by_key and existing_by_key[key]:
            matched_existing = existing_by_key[key].pop(0)

        candidates = matched_existing.candidates if matched_existing else []
        if matched_existing:
            reused_count += 1
        else:
            changed_count += 1

        merged.append(
            DetailedMention(
                text=revised.text,
                type=revised.type,
                label_pred=revised.label_pred,
                attrs=revised.attrs,
                selected_candidate_iri=(
                    revised.selected_candidate_iri
                    or (
                        matched_existing.selected_candidate_iri
                        if matched_existing
                        else None
                    )
                ),
                candidates=candidates,
            )
        )

    removed_count = sum(len(items) for items in existing_by_key.values())
    changed_count += removed_count
    return merged, reused_count, changed_count


def build_linked_mentions_from_candidates(mentions: list[Any]) -> LinkedMentions:
    linked: list[LinkedMention] = []
    for mention in mentions:
        if not mention.candidates:
            continue

        selected_iri = (getattr(mention, "selected_candidate_iri", None) or "").strip()
        selected = None
        if selected_iri:
            selected = next(
                (
                    candidate
                    for candidate in mention.candidates
                    if candidate.uri == selected_iri
                ),
                None,
            )

        best = selected or max(
            mention.candidates,
            key=lambda candidate: candidate.score or 0,
        )
        linked.append(
            LinkedMention(
                text=mention.text,
                type=mention.type,
                label_pred=mention.label_pred,
                attrs=mention.attrs,
                iri=best.uri,
            )
        )

    return LinkedMentions(mentions=linked)
