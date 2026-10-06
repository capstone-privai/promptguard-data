"""Dataset records. Offsets are Python string (code point) offsets, start inclusive, end exclusive."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Where the text passes through opencode. Must equal scripts/build_dataset.py CHANNELS;
# test_system_contract checks this.
CHANNELS: tuple[str, ...] = ("prompt", "instructions", "tool_input", "tool_output")

# Must equal scripts/build_dataset.py TYPES and promptguard.common.schema.CandidateType;
# test_system_contract checks both.
GOLD_TYPES: tuple[str, ...] = ("PASSWORD", "TOKEN", "ACCESS_KEY", "PRIVATE_KEY", "SECRET")

# meta.allowed_use purposes an evaluation run can require (see scripts/dataset_policy.py).
USES: tuple[str, ...] = ("rule_eval", "ml_eval")


@dataclass(frozen=True)
class GoldSpan:
    item_id: int
    span_id: int
    start: int
    end: int
    type: str


@dataclass(frozen=True)
class Item:
    item_id: int  # unique within its session only
    turn_id: str
    channel: str
    text: str


@dataclass(frozen=True)
class Session:
    session_id: str
    items: list[Item]
    gold: list[GoldSpan]
    meta: dict[str, Any] = field(default_factory=dict)

    def gold_for(self, item_id: int) -> list[GoldSpan]:
        return sorted((span for span in self.gold if span.item_id == item_id), key=lambda span: (span.start, span.end))
