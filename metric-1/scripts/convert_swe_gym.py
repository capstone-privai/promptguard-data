"""Convert SWE-Gym/OpenHands-SFT-Trajectories (OpenHands solving GitHub issues of Python repositories) into our
session format.

Run from the repository root, after downloading the dataset (see metric-1/README_SWE-Gym.md):
  python metric-1/scripts/convert_swe_gym.py --swe-gym ../SWE-Gym-OpenHands-SFT-Trajectories

Third-party data: origin=external, allowed_use=[rule_eval, ml_eval]. Needs pyarrow.

Writes, under --out (default metric-1/):
  data_test/sessions_from_SWE-Gym.jsonl  one session per trajectory (491)
  data_answer/gold_from_SWE-Gym.jsonl    gold spans (same schema as gold.jsonl)
  labels_from_SWE-Gym.jsonl              every reviewed candidate with its verdict (no values)

Channels: the system message -> instructions; the first user message (the uploaded repository and the issue) and
the harness's "Please continue working" nudges -> prompt; each function call the assistant wrote, verbatim
(<function=execute_bash><parameter=command>...) -> tool_input; "EXECUTION RESULT of [...]" messages -> tool_output.
The assistant's own text has no channel and is left out, as in the privesc conversion. turn_id counts assistant
messages. An item longer than MAX_ITEM_CHARS keeps its first MAX_ITEM_CHARS characters.

Gold: no credentials were planted, so gold comes from a review of candidates, as for openhands-feedback (see
review_candidates.py and metric-1/reviews/SWE-Gym.jsonl).
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
NAME = "SWE-Gym"
SOURCE = "swe-gym"
HF_REPO = "SWE-Gym/OpenHands-SFT-Trajectories"
REVISION = "4aaa5a4a4b5861f4799d2336908760c190ac3b17"
DATA_FILE = "data/train.success.oss-00000-of-00001.parquet"
MAX_ITEM_CHARS = 30000
CALL = re.compile(r"<function=[\w-]+>.*?(?:</function>|$)", re.S)


def items_of(messages: list[dict]) -> list[tuple[str, str, str]]:
    out, assistants = [], 0
    for n, msg in enumerate(messages):
        role, text = msg["role"], msg["content"] or ""
        turn = f"t{max(assistants - 1, 0)}"
        if role == "system":
            out.append((turn, "instructions", text))
        elif role == "user":
            channel = "tool_output" if text.startswith("EXECUTION RESULT of [") else "prompt"
            out.append((turn, channel, text))
        elif role == "assistant":
            assistants += 1
            for call in CALL.findall(text):
                out.append((f"t{assistants - 1}", "tool_input", call))
        else:
            raise ValueError(f"unknown role {role!r}")
    return [(t, c, text[:MAX_ITEM_CHARS]) for t, c, text in out if text.strip()]


def instance_of(messages: list[dict]) -> str:
    m = re.search(r"/workspace/([A-Za-z0-9_.-]+)", messages[1]["content"]) if len(messages) > 1 else None
    return m.group(1) if m else "unknown"


def sessions_of(root: Path) -> list[dict]:
    import pyarrow.parquet as pq  # only the converters of parquet sources need it

    path = root / DATA_FILE
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing; download {HF_REPO} first (README_{NAME}.md)")
    sessions = []
    for n, row in enumerate(pq.read_table(path).to_pylist()):
        messages = row["messages"]
        instance = instance_of(messages)
        items = [{"item_id": i, "turn_id": turn, "channel": channel, "text": text}
                 for i, (turn, channel, text) in enumerate(items_of(messages))]
        sessions.append({"session_id": f"swe-gym-{n:03d}", "items": items, "meta": {
            "dataset_version": f"{SOURCE}@{REVISION[:12]}", "source": SOURCE,
            "origin": "external", "allowed_use": ALLOWED_USE["external"],
            "group_id": f"swe-gym-{instance.split('__')[0]}",
            "instance": instance, "upstream_row": n, "license": f"MIT ({HF_REPO})",
        }})
    return sessions


def convert(root: Path, review: dict | None = None):
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
    parser.add_argument("--swe-gym", type=Path, default=REPO_ROOT.parent / "SWE-Gym-OpenHands-SFT-Trajectories",
                        help=f"local copy of {HF_REPO} at revision {REVISION[:12]}")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(write_outputs(args.swe_gym, args.out), indent=2))


if __name__ == "__main__":
    main()
