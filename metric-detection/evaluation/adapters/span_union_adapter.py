"""Rule findings ∪ full-text ML findings, merged only where masking intervals overlap."""
from __future__ import annotations

import hashlib
import math
import time

from evaluation.adapters.base import ItemOutput, passthrough
from evaluation.adapters.promptguard_adapter import CHANNEL_MAP, ModFailure, ModSession, PromptGuardAdapter, _code_point_offsets
from evaluation.run import ScoringError


def union_findings(text, rule_result, ml_spans):
    # A bad rule result cannot be repaired by ML; both stages must succeed.
    ModSession()._redact(text, rule_result)
    offsets = _code_point_offsets(text)
    intervals = []
    for finding in rule_result["findings"]:
        a, b = finding["start"], finding["end"]
        intervals.append({"start": offsets[a] if offsets else a, "end": offsets[b] if offsets else b,
                          "type": finding.get("type", "CREDENTIAL")})
    rule_bounds = {(span["start"], span["end"]) for span in intervals}
    for span in ml_spans:
        if (not isinstance(span, dict) or type(span.get("start")) is not int or type(span.get("end")) is not int
                or not 0 <= span["start"] < span["end"] <= len(text)
                or type(span.get("score")) not in (int, float) or not math.isfinite(span["score"])
                or not 0 <= span["score"] <= 1):
            raise ValueError("invalid ML span")
        if (span["start"], span["end"]) not in rule_bounds:
            intervals.append({"start": span["start"], "end": span["end"], "type": "SECRET"})
    merged = []
    for span in sorted(intervals, key=lambda s: (s["start"], s["end"])):
        if merged and span["start"] < merged[-1]["end"]:
            previous = merged[-1]
            previous["end"] = max(previous["end"], span["end"])
            if previous["type"] != span["type"]:
                previous["type"] = "SECRET"
        else:
            merged.append(dict(span))
    findings = []
    for span in merged:
        a, b = span["start"], span["end"]
        findings.append({"start": len(text[:a].encode("utf-16-le")) // 2,
                         "end": len(text[:b].encode("utf-16-le")) // 2,
                         "offset_unit": "utf16_code_units", "type": span["type"],
                         "value_hash": hashlib.sha256(text[a:b].encode()).hexdigest()})
    counts = {"rule": len(rule_result["findings"]), "ml": len(ml_spans), "final": len(findings),
              "ml_only": sum(not any(max(s["start"], a) < min(s["end"], b) for a, b in rule_bounds)
                             for s in ml_spans)}
    return {**rule_result, "findings": findings}, counts


class SpanUnionAdapter(PromptGuardAdapter):
    name = "promptguard-span-union"

    def __init__(self, classifier, worker=None, debug=False):
        super().__init__(worker=worker, debug=debug)
        self.classifier = classifier
        self.counts = dict.fromkeys(("rule", "ml", "final", "ml_only"), 0)

    def describe(self):
        return {**super().describe(), "pipeline": "detector-span-union", "second_stage": self.classifier.describe(),
                "span_counts": dict(self.counts), "remask": True}

    def scan_union(self, text, source, *, session_id, item_id, turn_id, channel):
        result = self._scan(text, source)
        ModSession()._redact(text, result)
        spans = self.classifier.predict_spans({"session_id": session_id, "item_id": item_id, "turn_id": turn_id,
                                              "channel": channel, "text": text, "offset_unit": "code_points"})
        combined, counts = union_findings(text, result, spans)
        for key, count in counts.items():
            self.counts[key] += count
        return combined

    def run_session(self, session):
        mod, outputs = ModSession(), {}
        for item in session.items:
            if item.channel not in CHANNEL_MAP:
                outputs[item.item_id] = passthrough(item.item_id, item.text)
                continue
            started = time.perf_counter()
            try:
                combined = self.scan_union(item.text, CHANNEL_MAP[item.channel], session_id=session.session_id,
                                           item_id=item.item_id, turn_id=item.turn_id, channel=item.channel)
                text, edits = mod.redact(item.text, combined)
            except (ModFailure, KeyError, ValueError, RuntimeError) as exc:
                raise ScoringError(session.session_id, item.item_id, f"span union failed ({type(exc).__name__})") from exc
            outputs[item.item_id] = ItemOutput(item.item_id, text, edits, (time.perf_counter() - started) * 1000)
        return outputs
