"""Wire dataset → adapter → scorer → aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.adapters.base import ItemOutput, SystemUnderTest
from evaluation.dataset.io import load_sessions
from evaluation.dataset.schema import TRAINING_SPLITS, Session
from evaluation.dataset.validate import ValidationIssue, validate_dataset
from evaluation.report.aggregate import aggregate
from evaluation.scorer.edits import EditError, VerificationError
from evaluation.scorer.span_scoring import ItemScore, score_item

ItemKey = tuple[str, int]  # (session_id, item_id)


class DatasetInvalidError(Exception):
    def __init__(self, issues: list[ValidationIssue]):
        super().__init__(f"dataset has {len(issues)} validation issue(s)")
        self.issues = issues


class ScoringError(Exception):
    """An adapter's output could not be scored. No partial metrics are produced."""

    def __init__(self, session_id: str, item_id: int | None, reason: str):
        super().__init__(f"session={session_id} item={'-' if item_id is None else item_id}: {reason}")
        self.session_id = session_id
        self.item_id = item_id
        self.reason = reason


@dataclass(frozen=True)
class RunResult:
    system: dict[str, Any]
    sessions: list[Session]
    outputs: dict[ItemKey, ItemOutput]
    scores: list[ItemScore]
    metrics: dict[str, Any]


def check_use(sessions: list[Session], use: str) -> list[ValidationIssue]:
    """Sessions whose meta.allowed_use does not include `use` (scripts/dataset_policy.py), and ML training sessions:
    a model must not be scored on what it was trained on, even if meta.allowed_use was edited."""
    issues = []
    for session in sessions:
        if session.meta.get("split") in TRAINING_SPLITS:
            issues.append(ValidationIssue(session.session_id, None, f"meta.split {session.meta['split']!r} is ML "
                                          "training data; evaluate on test or test_ood"))
        elif use not in (session.meta.get("allowed_use") or []):
            issues.append(ValidationIssue(session.session_id, None, f"meta.allowed_use does not include {use!r}"))
    return issues


def load_dataset(sessions_path: str | Path, gold_path: str | Path, use: str | None = None) -> list[Session]:
    issues = validate_dataset(sessions_path, gold_path)
    if issues:
        raise DatasetInvalidError(issues)
    sessions = load_sessions(sessions_path, gold_path)
    if use is not None and (issues := check_use(sessions, use)):
        raise DatasetInvalidError(issues)
    return sessions


def evaluate_sessions(sessions: list[Session], adapter: SystemUnderTest) -> RunResult:
    outputs: dict[ItemKey, ItemOutput] = {}
    scores: list[ItemScore] = []
    for session in sessions:
        produced = adapter.run_session(session)
        expected = [item.item_id for item in session.items]
        if set(produced) != set(expected):
            stray = sorted(set(produced) ^ set(expected))
            raise ScoringError(session.session_id, stray[0], "adapter output does not cover exactly the session's items")
        for item in session.items:
            output = produced[item.item_id]
            try:
                scores.append(score_item(session.session_id, item.item_id, item.channel, item.text, output.text,
                                         output.edits, session.gold_for(item.item_id)))
            except (EditError, VerificationError) as exc:
                raise ScoringError(session.session_id, item.item_id, str(exc)) from exc
            outputs[(session.session_id, item.item_id)] = output
    elapsed = {key: output.elapsed_ms for key, output in outputs.items()}
    return RunResult(adapter.describe(), sessions, outputs, scores, aggregate(sessions, scores, elapsed))


def evaluate(sessions_path: str | Path, gold_path: str | Path, adapter: SystemUnderTest) -> RunResult:
    return evaluate_sessions(load_dataset(sessions_path, gold_path), adapter)
