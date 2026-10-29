"""Expose committed task CSVs as legacy batches without inventing provenance."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    sources = (("archive_01_full_234", "metric-task/results/runs.csv"),
               ("archive_02_capture_trial_30", "metric-task/results/capture_trial/runs.csv"))
    for name, relative in sources:
        source = ROOT / relative
        content = source.read_bytes()
        with source.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        destination = ROOT / "runs" / "metric-task" / name
        destination.mkdir(parents=True, exist_ok=True)
        meta = {
            "model": next((row["model"] for row in rows if row.get("model")), None),
            "reps": max(int(row["rep"]) for row in rows),
            "started_at": None,
            "system_commit": None,
            "data_commit": None,
            "import_source": relative,
            "import_source_sha256": hashlib.sha256(content).hexdigest(),
            "note": "Archived CSV; original batch metadata and checkout provenance were not recorded.",
        }
        output = {"runs.csv": content, "batch.json": (json.dumps(meta, indent=2) + "\n").encode()}
        for filename, data in output.items():
            target = destination / filename
            if target.is_file() and target.read_bytes() != data:
                raise FileExistsError(f"preserving existing different batch: {target}")
        for filename, data in output.items():
            (destination / filename).write_bytes(data)
        print(f"Imported {len(rows)} archived runs: {name} (provenance unknown)")


if __name__ == "__main__":
    main()
