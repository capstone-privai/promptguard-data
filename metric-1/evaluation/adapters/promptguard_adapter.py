"""Run dataset items through the exact runtime assembly (promptguard.pipeline).

Import this only after system_root.use_system_root() has put the PromptGuard checkout on sys.path.
"""

from __future__ import annotations

import time
from typing import Any

from evaluation.adapters.base import ItemOutput, passthrough
from evaluation.adapters.threshold import ThresholdPredictor
from evaluation.dataset.schema import Session
from evaluation.scorer.edits import Edit
from promptguard.decision.base import Predictor
from promptguard.decision.registry import load_predictor
from promptguard.pipeline import PROCESSED_CHANNELS, build_task_context, process_output
from promptguard.redaction.placeholders import PlaceholderRegistry

_WARMUP_TEXT = "DB_PASSWORD=warmup123\n"

# Dataset channel (opencode) → the system's channel name. The system (Codex Bash hook) sees
# stdout and stderr separately; opencode's bash tool returns them merged as one tool_output.
# Channels without an entry, or whose target the system does not process, pass through.
CHANNEL_MAP: dict[str, str] = {"tool_output": "stdout"}


def system_channel(channel: str) -> str | None:
    """The system channel an item is processed as, or None if the system does not process it."""
    target = CHANNEL_MAP.get(channel)
    return target if target in PROCESSED_CHANNELS else None


class PromptGuardAdapter:
    name = "promptguard"

    def __init__(self, predictor: str | Predictor = "mock", threshold: float | None = None, debug: bool = False):
        base = load_predictor(predictor) if isinstance(predictor, str) else predictor
        self.predictor_name = predictor if isinstance(predictor, str) else type(predictor).__name__
        self.threshold = threshold
        self.predictor: Predictor = base if threshold is None else ThresholdPredictor(base, threshold)
        self.debug = debug
        self._warm_up()

    def _warm_up(self) -> None:
        # The first call loads CredSweeper; keep that out of the recorded latencies.
        if not PROCESSED_CHANNELS:
            return
        process_output(
            _WARMUP_TEXT, session_id="__warmup__", turn_id="", operation_id="__warmup__",
            channel=PROCESSED_CHANNELS[0], task_context=build_task_context("", ""),
            predictor=self.predictor, allocate=PlaceholderRegistry().allocator("__warmup__"),
        )

    def describe(self) -> dict[str, Any]:
        return {
            "system": self.name,
            "predictor": self.predictor_name,
            "threshold": self.threshold,
            "processed_channels": [channel for channel in CHANNEL_MAP if system_channel(channel)],
            "channel_map": dict(CHANNEL_MAP),
            "system_processed_channels": list(PROCESSED_CHANNELS),
        }

    def run_session(self, session: Session) -> dict[int, ItemOutput]:
        registry = PlaceholderRegistry()
        task_context = build_task_context("", "")
        outputs: dict[int, ItemOutput] = {}
        for item in session.items:
            if item.channel == "prompt":
                # The daemon replaces the session task on every new prompt; the prompt itself is not processed.
                task_context = build_task_context(item.text, item.turn_id)
                outputs[item.item_id] = passthrough(item.item_id, item.text)
            elif channel := system_channel(item.channel):
                started = time.perf_counter()
                result = process_output(
                    item.text, session_id=session.session_id, turn_id=item.turn_id, operation_id=str(item.item_id),
                    channel=channel, task_context=task_context, predictor=self.predictor,
                    allocate=registry.allocator(session.session_id),
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                edits = [Edit(start=edit.start, end=edit.end, replacement=edit.replacement) for edit in result.edits]
                debug = None
                if self.debug:
                    debug = {
                        "candidates": [candidate.to_dict() for candidate in result.candidates],
                        "predictions": [prediction.to_dict() for prediction in result.predictions],
                        "system_edits": [edit._asdict() for edit in result.edits],
                    }
                outputs[item.item_id] = ItemOutput(item.item_id, result.text, edits, elapsed_ms, debug)
            else:
                outputs[item.item_id] = passthrough(item.item_id, item.text)
        return outputs
