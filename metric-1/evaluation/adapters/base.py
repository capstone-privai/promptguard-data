from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from evaluation.dataset.schema import Session
from evaluation.scorer.edits import Edit


@dataclass(frozen=True)
class ItemOutput:
    item_id: int
    text: str  # what the model would receive
    edits: list[Edit]  # original-text coordinates; the scorer verifies them against `text`
    elapsed_ms: float | None = None  # processing time; None for channels the system does not process
    debug: dict[str, Any] | None = None  # only with --debug; may contain raw secrets


class SystemUnderTest(Protocol):
    name: str

    def describe(self) -> dict[str, Any]:
        """Configuration recorded in run_meta.json."""
        ...

    def run_session(self, session: Session) -> dict[int, ItemOutput]:
        """Return an output for every item in the session, keyed by item_id.

        Unprocessed channels return the original text with no edits. Edits must be reported
        as applied, never reconstructed from the output text.
        """
        ...


def passthrough(item_id: int, text: str) -> ItemOutput:
    return ItemOutput(item_id=item_id, text=text, edits=[])


def select_non_overlapping(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Keep the longest span among overlaps, then the earliest; return them sorted by start."""
    selected: list[tuple[int, int]] = []
    for start, end in sorted(set(spans), key=lambda span: (-(span[1] - span[0]), span[0])):
        if not any(start < prior_end and prior_start < end for prior_start, prior_end in selected):
            selected.append((start, end))
    return sorted(selected)
