"""Write the scorer's files for the CredData-trajectory test set from an exported handoff folder.

creddata_export.py keeps the CredData Category as span.type. The scorer (metric-detection/evaluation) reads the five
gold types, so each span gets convert_creddata.gold_type(category) as span.type and keeps the Category as
span.category. Sessions are copied as they are. Only a test-split handoff is accepted.

  python3 metric-detection/scripts/creddata_eval_set.py --handoff runs/creddata-trajectory-handoff/test-v1
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil

from convert_creddata import gold_type

BASE = Path(__file__).resolve().parents[1]
NAME = "from_CredData-trajectory"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=BASE, help="folder holding data_test/ and data_answer/")
    args = parser.parse_args()
    manifest = json.loads((args.handoff / "manifest.json").read_text())
    if manifest["split"] != "test" or manifest["variants_per_session"]:
        parser.error("the evaluation set is the recorded test split only")
    sessions, gold = args.out / "data_test" / f"sessions_{NAME}.jsonl", args.out / "data_answer" / f"gold_{NAME}.jsonl"
    for path in (sessions, gold):
        path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.handoff / "sessions_test.jsonl", sessions)
    types = Counter()
    with (args.handoff / "gold_test.jsonl").open(encoding="utf-8") as source, gold.open("w", encoding="utf-8") as out:
        for line in source:
            row = json.loads(line)
            category = row["span"]["type"]
            row["span"] = {**row["span"], "type": gold_type(category, ""), "category": category}
            types[row["span"]["type"]] += 1
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"sessions": str(sessions), "gold": str(gold), "session_count": manifest["sessions"],
                      "gold_spans": sum(types.values()), "by_type": dict(sorted(types.items()))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
