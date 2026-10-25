"""Dataset records. Offsets are Python string (code point) offsets, start inclusive, end exclusive."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Where the text sits in the model's input/output (agent-agnostic). Must equal scripts/dataset_build.py CHANNELS;
# test_system_contract checks this.
CHANNELS: tuple[str, ...] = ("prompt", "instructions", "tool_input", "tool_output")

# The channels metric-detection scores, for every system. tool_input is text the model wrote (e.g. a shell command):
# nothing to mask there; placeholders in it are restored to the real values just before execution. Its items
# and gold stay in the data, and scoring leaves its gold, its edits and its lines out of every metric.
# PromptGuard's CHANNEL_MAP, the CredSweeper adapter's default channels and scripts/run_gitleaks.py
# SCORED_CHANNELS must equal this; test_system_contract checks.
SCORED_CHANNELS: tuple[str, ...] = ("prompt", "instructions", "tool_output")

# Must equal scripts/dataset_build.py TYPES and promptguard.common.schema.CandidateType;
# test_system_contract checks both.
GOLD_TYPES: tuple[str, ...] = ("PASSWORD", "TOKEN", "ACCESS_KEY", "PRIVATE_KEY", "SECRET")

# meta.allowed_use purposes an evaluation run can require (see scripts/dataset_policy.py).
USES: tuple[str, ...] = ("rule_eval", "ml_eval")

# meta.split values of the ML training side (scripts/dataset_policy.py TRAIN_SPLITS): never scored, whatever
# meta.allowed_use says. test_system_contract checks it equals the policy.
TRAINING_SPLITS: tuple[str, ...] = ("train", "val")


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
