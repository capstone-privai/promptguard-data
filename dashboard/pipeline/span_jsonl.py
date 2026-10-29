"""Serve a full-text span model over versioned JSONL, optionally as a candidate overlap gate.

This is an explicit overlap gate, not a trained candidate classification head. A rule candidate
is MASK if it intersects a predicted secret span. Boundaries remain the rule's boundaries;
ML-only findings are not added. The saved model threshold is used without recalibration.
"""
from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
import sys
import time


def decide(request: dict, spans: list[dict]) -> list[dict]:
    if (not isinstance(request, dict) or type(request.get("version")) is not int or request["version"] != 1
            or type(request.get("request_id")) is not int or request.get("offset_unit") != "code_points"
            or not isinstance(request.get("text"), str) or not isinstance(request.get("candidates"), list)):
        raise ValueError("invalid candidate inference request")
    length = len(request["text"])
    if not isinstance(spans, list) or not all(isinstance(span, dict)
            and type(span.get("start")) is int and type(span.get("end")) is int
            and 0 <= span["start"] < span["end"] <= length for span in spans):
        raise ValueError("invalid model span")
    decisions, seen = [], set()
    for candidate in request["candidates"]:
        if (not isinstance(candidate, dict) or type(candidate.get("id")) is not int
                or candidate["id"] in seen or type(candidate.get("start")) is not int
                or type(candidate.get("end")) is not int
                or not 0 <= candidate["start"] < candidate["end"] <= length):
            raise ValueError("invalid rule candidate")
        seen.add(candidate["id"])
        overlap = any(max(candidate["start"], span["start"]) < min(candidate["end"], span["end"])
                      for span in spans)
        decisions.append({"id": candidate["id"], "label": "MASK" if overlap else "KEEP"})
    return decisions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--source", required=True, help="pinned promptguard-model src/ directory")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--mode", choices=("candidate", "span_union"), default="candidate")
    parser.add_argument("--progress-every", type=int, default=0, help="emit counts only to stderr (0: disabled)")
    args = parser.parse_args(argv)
    if args.threads < 1:
        parser.error("--threads must be positive")
    sys.path.insert(0, str(Path(args.source).resolve()))
    with contextlib.redirect_stdout(sys.stderr):
        import torch
        from privai_model.ml_span.runtime import MLSpanDetector
        torch.set_num_threads(args.threads)
        torch.set_num_interop_threads(1)
        detector = MLSpanDetector(Path(args.checkpoint).resolve(), device="cpu")
    processed, started = 0, time.perf_counter()
    for line in sys.stdin:
        request = json.loads(line)
        with contextlib.redirect_stdout(sys.stderr):
            if args.mode == "candidate":
                decide(request, [])
                spans = detector.scan_text(request["text"]) if request["candidates"] else []
                result = {"decisions": decide(request, spans)}
            else:
                if (not isinstance(request, dict) or type(request.get("version")) is not int or request["version"] != 1
                        or type(request.get("request_id")) is not int or request.get("offset_unit") != "code_points"
                        or not isinstance(request.get("text"), str)):
                    raise ValueError("invalid span inference request")
                result = {"offset_unit": "code_points", "spans": detector.scan_text(request["text"])}
        print(json.dumps({"version": 1, "request_id": request["request_id"], **result}), flush=True)
        processed += 1
        if args.progress_every > 0 and processed % args.progress_every == 0:
            print(json.dumps({"event": "ml_progress", "requests_processed": processed,
                              "seconds": round(time.perf_counter() - started, 1)}), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
