"""Versioned local model bundles and a persistent JSONL KEEP/MASK inference process.

Inference stays outside evaluation/: the scorer has no subprocess/network dependencies.
All model weights, tokenizer, feature code and inference code belong inside the bundle.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import queue
import shutil
import subprocess
import threading
from typing import Any

from evaluation.dataset.io import file_sha256

PROTOCOL_VERSION = 1
MAX_RESPONSE = 4 * 1024 * 1024
_HASHES: dict[tuple, str] = {}


class InferenceTimeout(RuntimeError):
    """A model did not answer before the configured request deadline."""


def bundle_hash(bundle: Path) -> str:
    digest, count = hashlib.sha256(), 0
    for path in sorted(bundle.rglob("*")):
        relative = path.relative_to(bundle)
        if "__pycache__" in relative.parts or ".git" in relative.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError("ML bundle must contain regular files, not symlinks")
        if path.is_file():
            stat = path.stat()
            key = (str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
            if key not in _HASHES:
                _HASHES[key] = file_sha256(path)
            digest.update(relative.as_posix().encode() + b"\0" + _HASHES[key].encode())
            count += 1
    if not count:
        raise ValueError("ML bundle is empty")
    return digest.hexdigest()


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    bundle: Path
    command: tuple[str, ...]
    timeout_seconds: float
    datasets: tuple[str, ...]
    fingerprint: str
    mode: str = "candidate"

    def metadata(self) -> dict[str, Any]:
        return {"model_id": self.model_id, "fingerprint": self.fingerprint, "protocol_version": PROTOCOL_VERSION,
                **({"mode": self.mode} if self.mode != "candidate" else {}),
                "datasets": list(self.datasets)}


def load_spec(path: str | Path) -> ModelSpec:
    path = Path(path).resolve()
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        model_id, command = config["model_id"], config["command"]
        bundle = (path.parent / config["bundle"]).resolve()
        timeout = config.get("timeout_seconds", 120)
        datasets = config.get("datasets", [])
        mode = config.get("mode", "candidate")
        if mode not in ("candidate", "span_union"):
            raise ValueError("ML mode must be candidate or span_union")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("ML model_id must be nonempty")
        if (not isinstance(command, list) or not command or
                not all(isinstance(arg, str) and arg for arg in command) or
                not any("{bundle}" in arg for arg in command)):
            raise ValueError("ML command must be an argv list using {bundle}")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("ML timeout_seconds must be positive and finite")
        if (not isinstance(datasets, list) or not all(isinstance(d, str) and d.startswith("sessions")
                and Path(d).name == d and not d.endswith(".jsonl") for d in datasets)
                or len(datasets) != len(set(datasets))):
            raise ValueError("ML datasets must be unique sessions file stems")
        if not bundle.is_dir():
            raise ValueError("ML bundle directory is missing")
        identity = {"model_id": model_id, "command": command, "timeout_seconds": timeout,
                    "datasets": sorted(datasets), "bundle_sha256": bundle_hash(bundle), "protocol_version": PROTOCOL_VERSION}
        if mode != "candidate":
            identity["mode"] = mode
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        return ModelSpec(model_id, bundle, tuple(command), timeout, tuple(sorted(datasets)), fingerprint, mode)
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid ML config; check model_id, bundle and command") from exc


def snapshot(spec: ModelSpec, directory: Path) -> Path:
    directory.mkdir(parents=True)
    shutil.copytree(spec.bundle, directory / "bundle", ignore=shutil.ignore_patterns("__pycache__", ".git", "*.pyc"))
    path = directory / "config.json"
    path.write_text(json.dumps({"model_id": spec.model_id, "bundle": "bundle", "command": spec.command,
                               "timeout_seconds": spec.timeout_seconds, "datasets": spec.datasets,
                               "mode": spec.mode}), encoding="utf-8")
    if load_spec(path).fingerprint != spec.fingerprint:
        raise ValueError("ML bundle changed while taking the evaluation snapshot")
    return path


class JsonlClassifier:
    """One subprocess per shard. stdout is protocol only; logs go to stderr. No shell is used."""
    mode = "candidate"

    def __init__(self, spec: ModelSpec):
        self.spec, self.sequence, self.closed = spec, 0, False
        self.requests, self.responses = queue.Queue(), queue.Queue()
        try:
            self.process = subprocess.Popen([arg.replace("{bundle}", str(spec.bundle)) for arg in spec.command],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                            encoding="utf-8", bufsize=1)
        except OSError as exc:
            raise ValueError("cannot start ML command; check its executable and dependencies") from exc
        self.thread = threading.Thread(target=self._exchange, daemon=True)
        self.thread.start()

    def _exchange(self):
        while (request := self.requests.get()) is not None:
            try:
                self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                self.process.stdin.flush()
                line = self.process.stdout.readline(MAX_RESPONSE + 1)
                if not line or len(line) > MAX_RESPONSE:
                    raise ValueError("missing or oversized ML response")
                self.responses.put((True, json.loads(line)))
            except (OSError, ValueError):
                self.responses.put((False, None))
                return

    def _response(self, request: dict[str, Any]) -> dict:
        if self.closed:
            raise RuntimeError("ML inference process is closed")
        self.sequence += 1
        self.requests.put({**request, "version": PROTOCOL_VERSION, "request_id": self.sequence})
        try:
            ok, response = self.responses.get(timeout=self.spec.timeout_seconds)
            if not ok or not isinstance(response, dict):
                raise ValueError("invalid ML JSONL response")
            if (type(response.get("version")) is not int or response["version"] != PROTOCOL_VERSION
                    or type(response.get("request_id")) is not int or response["request_id"] != self.sequence):
                raise ValueError("ML response version or request_id mismatch")
            return response
        except queue.Empty as exc:
            self.close()
            raise InferenceTimeout("ML inference timed out; no results were published") from exc
        except ValueError:
            self.close()
            raise

    def predict(self, request: dict[str, Any]) -> list[str]:
        response = self._response(request)
        try:
            decisions = response.get("decisions")
            if not isinstance(decisions, list) or len(decisions) != len(request["candidates"]):
                raise ValueError("ML response must decide every candidate")
            labels = {}
            for decision in decisions:
                if (not isinstance(decision, dict) or type(decision.get("id")) is not int
                        or decision["id"] in labels or decision.get("label") not in ("KEEP", "MASK")):
                    raise ValueError("invalid ML candidate decision")
                labels[decision["id"]] = decision["label"]
            if set(labels) != {candidate["id"] for candidate in request["candidates"]}:
                raise ValueError("ML candidate ids do not match")
            return [labels[candidate["id"]] for candidate in request["candidates"]]
        except ValueError:
            self.close()
            raise

    def describe(self) -> dict[str, Any]:
        return self.spec.metadata()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.requests.put(None)
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        self.thread.join(timeout=5)
        for pipe in (self.process.stdin, self.process.stdout):
            try:
                pipe.close()
            except OSError:
                pass


class JsonlSpanDetector(JsonlClassifier):
    """Full-text span protocol. ML is called even when the rule detector found nothing."""
    mode = "span_union"

    def predict_spans(self, request: dict[str, Any]) -> list[dict]:
        response = self._response(request)
        try:
            spans = response.get("spans")
            if (response.get("offset_unit") != "code_points" or not isinstance(spans, list)
                    or not all(isinstance(span, dict) and type(span.get("start")) is int
                               and type(span.get("end")) is int
                               and 0 <= span["start"] < span["end"] <= len(request["text"])
                               and type(span.get("score")) in (int, float) and math.isfinite(span["score"])
                               and 0 <= span["score"] <= 1 for span in spans)):
                raise ValueError("invalid ML span response")
            return spans
        except ValueError:
            self.close()
            raise


def inference(spec: ModelSpec):
    return JsonlSpanDetector(spec) if spec.mode == "span_union" else JsonlClassifier(spec)

