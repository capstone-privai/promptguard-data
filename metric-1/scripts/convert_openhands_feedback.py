"""Convert all-hands/openhands-feedback (real OpenHands sessions shared by their users) into our session format.

Run from the repository root, after downloading the dataset (see metric-1/README_openhands-feedback.md):
  python metric-1/scripts/convert_openhands_feedback.py --openhands ../openhands-feedback

Third-party data: origin=external, allowed_use=[rule_eval, ml_eval]. Needs pyarrow.

Writes, under --out (default metric-1/):
  data_test/sessions_from_openhands-feedback.jsonl  one session per shared trajectory
  data_answer/gold_from_openhands-feedback.jsonl    gold spans (same schema as gold.jsonl)
  labels_from_openhands-feedback.jsonl              every reviewed candidate with its verdict (no values)

Channels: a user message -> prompt; an agent action's argument (a shell command, IPython code, browser actions, a
file path to read, the content written to a file) -> tool_input; the observation that answers it (command output,
IPython output, page text, file content, edit diff, error) -> tool_output. Agent messages have no channel and are
left out, as in the privesc conversion; so are state changes, plans and the environment's initialization. turn_id
counts user messages. An item longer than MAX_ITEM_CHARS keeps its first MAX_ITEM_CHARS characters (the size at
which Claude Code also cuts a tool result).

Gold: the upstream maintainers reviewed the data and removed sensitive information, so little is left.
Candidates come from CredSweeper, gitleaks and the regular expressions of review_candidates.py; each distinct
candidate value was judged with the metric 1 definition (metric-1/README.md). The verdicts are kept in REVIEW_FILE
as the value's SHA-256 and one place it occurs, never the value. Only verdict "credential" becomes gold, at every
occurrence of the value in that session; the other verdicts go to the labels file for over-masking analysis.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from dataset_build import write_jsonl
from dataset_policy import ALLOWED_USE
from review_candidates import apply_review, load_review

REPO_ROOT = Path(__file__).resolve().parents[2]
NAME = "openhands-feedback"
HF_REPO = "all-hands/openhands-feedback"
REVISION = "facf45600d625510b98222ec584a8c9ac59272a2"
DATA_FILE = "data/train-00000-of-00001.parquet"
MAX_ITEM_CHARS = 30000
ARGUMENT = {"run": "command", "run_ipython": "code", "browse_interactive": "browser_actions", "browse": "url",
            "read": "path", "write": "content", "edit": "content"}


def extras(step: dict) -> dict:
    try:
        value = json.loads(step.get("extras") or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def items_of(trajectory: list[dict]) -> list[tuple[str, str, str]]:
    """(turn_id, channel, text) per step, in order."""
    out, turn = [], -1
    for step in trajectory:
        source, action, observation = step.get("source"), step.get("action"), step.get("observation")
        if source == "user" and action == "message":
            turn += 1
            out.append((f"t{max(turn, 0)}", "prompt", step.get("content") or ""))
        elif source == "agent" and action in ARGUMENT:
            out.append((f"t{max(turn, 0)}", "tool_input", str(extras(step).get(ARGUMENT[action]) or "")))
        elif observation not in (None, "null", "agent_state_changed", "user_rejected") and step.get("content"):
            out.append((f"t{max(turn, 0)}", "tool_output", step["content"]))
    return [(t, c, text[:MAX_ITEM_CHARS]) for t, c, text in out if text.strip()]


def read_rows(root: Path) -> list[dict]:
    import pyarrow.parquet as pq  # only the converters of parquet sources need it

    path = root / DATA_FILE
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing; download {HF_REPO} first (README_{NAME}.md)")
    return pq.read_table(path, columns=["timestamp", "feedback", "trajectory"]).to_pylist()


def sessions_of(root: Path) -> list[dict]:
    sessions = []
    for n, row in enumerate(read_rows(root)):
        items = [{"item_id": i, "turn_id": turn, "channel": channel, "text": text}
                 for i, (turn, channel, text) in enumerate(items_of(row["trajectory"]))]
        if not items:
            continue
        sessions.append({"session_id": f"openhands-{n:03d}", "items": items, "meta": {
            "dataset_version": f"{NAME}@{REVISION[:12]}", "source": NAME,
            "origin": "external", "allowed_use": ALLOWED_USE["external"], "group_id": f"openhands-{n:03d}",
            "upstream_row": n, "feedback": row["feedback"], "timestamp": str(row["timestamp"]),
            "license": f"MIT ({HF_REPO})",
        }})
    return sessions


def convert(root: Path, review: dict[tuple[str, str], dict] | None = None):
    sessions = sessions_of(root)
    gold, labels, stats = apply_review(sessions, load_review(NAME) if review is None else review, NAME)
    return sessions, gold, labels, stats


def write_outputs(root: Path, out: Path) -> dict:
    sessions, gold, labels, stats = convert(root)
    for sub in ("data_test", "data_answer"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "data_test" / f"sessions_from_{NAME}.jsonl", sessions)
    write_jsonl(out / "data_answer" / f"gold_from_{NAME}.jsonl", gold)
    write_jsonl(out / f"labels_from_{NAME}.jsonl", labels)
    return {"sessions": len(sessions), "items": sum(len(s["items"]) for s in sessions),
            "items_by_channel": dict(Counter(i["channel"] for s in sessions for i in s["items"])),
            "gold_spans": len(gold), "gold_by_type": dict(Counter(g["span"]["type"] for g in gold)),
            **dict(sorted(stats.items()))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--openhands", type=Path, default=REPO_ROOT.parent / NAME,
                        help=f"local copy of {HF_REPO} at revision {REVISION[:12]}")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(write_outputs(args.openhands, args.out), indent=2))


if __name__ == "__main__":
    main()
