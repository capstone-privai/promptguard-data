"""Detector candidates → KEEP/MASK → final edits. The classifier never receives gold labels."""
from __future__ import annotations

import time
from typing import Any, Protocol

from evaluation.adapters.base import ItemOutput, passthrough
from evaluation.adapters.promptguard_adapter import CHANNEL_MAP, ModFailure, ModSession, PromptGuardAdapter, _code_point_offsets
from evaluation.dataset.schema import Session
from evaluation.run import ScoringError


class KeepMaskClassifier(Protocol):
    def predict(self, request: dict[str, Any]) -> list[str]: ...
    def describe(self) -> dict[str, Any]: ...


def classify_findings(classifier: KeepMaskClassifier, text: str, result: dict, *,
                      session_id: str, item_id: int, turn_id: str | int, channel: str) -> tuple[dict, list[str]]:
    """Validate detector spans, classify in code points, and retain only MASK findings.

    Shared by quality evaluation and the timed HTTP worker so KEEP/MASK means the same in both tracks.
    """
    ModSession()._redact(text, result)
    offsets = _code_point_offsets(text)
    candidates = []
    for index, finding in enumerate(result["findings"]):
        start, end = finding["start"], finding["end"]
        if offsets is not None:
            start, end = offsets[start], offsets[end]
        candidates.append({"id": index, "start": start, "end": end,
                           "type": finding.get("type"), "rule_id": finding.get("rule_id")})
    request = {"session_id": session_id, "item_id": item_id, "turn_id": turn_id,
               "channel": channel, "text": text, "offset_unit": "code_points", "candidates": candidates}
    labels = classifier.predict(request) if candidates else []
    if (not isinstance(labels, list) or len(labels) != len(candidates)
            or any(label not in ("KEEP", "MASK") for label in labels)):
        raise ValueError("classifier must return one KEEP/MASK per candidate")
    return {**result, "findings": [finding for finding, label in zip(result["findings"], labels) if label == "MASK"]}, labels


class TwoStageAdapter(PromptGuardAdapter):
    name = "promptguard-ml"

    def __init__(self, classifier: KeepMaskClassifier, worker=None, debug: bool = False):
        super().__init__(worker=worker, debug=debug)
        self.classifier = classifier
        self.counts = {"candidates": 0, "keep": 0, "mask": 0}

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "pipeline": "detector-ml", "second_stage": self.classifier.describe(),
                "candidate_counts": dict(self.counts), "remask": False}

    def run_session(self, session: Session) -> dict[int, ItemOutput]:
        mod, outputs = ModSession(), {}
        for item in session.items:
            source = CHANNEL_MAP.get(item.channel)
            if source is None:
                outputs[item.item_id] = passthrough(item.item_id, item.text)
                continue
            started = time.perf_counter()
            result = self._scan(item.text, source)
            try:
                filtered, labels = classify_findings(self.classifier, item.text, result, session_id=session.session_id,
                                                    item_id=item.item_id, turn_id=item.turn_id, channel=item.channel)
                # No reverse-map propagation: it would override KEEP or mask text ML never classified.
                text, edits = mod._redact(item.text, filtered)
            except (ModFailure, KeyError, ValueError, RuntimeError) as exc:
                raise ScoringError(session.session_id, item.item_id,
                                   f"two-stage inference failed ({type(exc).__name__})") from exc
            self.counts["candidates"] += len(labels)
            self.counts["mask"] += labels.count("MASK")
            self.counts["keep"] += labels.count("KEEP")
            debug = {"source": source, "result": result, "decisions": labels} if self.debug else None
            outputs[item.item_id] = ItemOutput(item.item_id, text, edits,
                                               (time.perf_counter() - started) * 1000, debug)
        return outputs
