#!/usr/bin/env python3
"""Writes planted.json next to each run of a batch: what the task planted, in which forms, and where.

metric-detection/scripts/convert_trajectory.py reads this file and nothing else from the task. It lists candidates;
label_rules decides which occurrences are gold. A decoy is listed too, because LABELING.md and a task's decoy can
disagree (a Stripe publishable key is a decoy here and gold there).

Values are deterministic, so this can run any time after the batch, with the generator the batch used:

    python3 metric-task/scripts/m2_planted.py runs/metric-task/<batch>
    M2_SECRETS=metric-task/scripts/m2_secrets_v1.py python3 metric-task/scripts/m2_planted.py runs/metric-task/<old batch>

The file holds fake credentials in real formats, so it stays under runs/, outside git.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2_tasks as mt  # noqa: E402

# Task fields that reach the session some other way than a workspace file.
SPEC_SOURCES = ("prompt", "append_system_prompt", "session_env", "mcp_fixture", "history", "worktree_changes",
                "final_commit")
WORKSPACE_CHANNELS = {"CLAUDE.md": "claude_md", ".claude/settings.json": "session_hook"}


def placements_in(template: str, source: str, path: str | None, task: mt.Task) -> list[tuple[str, str, dict]]:
    """(secret or decoy, name, placement) per reference in a template, with offsets into the text as built."""
    out, shift = [], 0
    for m in mt.SECRET_REF.finditer(template):
        role, name = m.groups()
        value = task.decoys[name] if role == "decoy" else task.secrets[name].value
        start = m.start() + shift
        line = task.fill(template[:m.start()]).count("\n") + 1
        out.append((role, name, {"source": source, "path": path, "line": line, "start": start, "end": start + len(value)}))
        shift += len(value) - len(m.group())
    return out


def leaves(value, where: str):
    """(where, text) for every string under a task field."""
    if isinstance(value, str):
        yield where, value
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from leaves(v, f"{where}[{i}]")
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from leaves(v, f"{where}.{k}")


def all_placements(task: mt.Task) -> list[tuple[str, str, dict]]:
    found = []
    src = task.dir / "workspace"
    for path in sorted(src.rglob("*")) if src.is_dir() else []:
        if not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(src).as_posix()
        found += placements_in(text, WORKSPACE_CHANNELS.get(rel, "file"), rel, task)
    for field in SPEC_SOURCES:
        for where, text in leaves(task.spec.get(field), field):
            found += placements_in(text, field, where, task)
    return found


def secret_forms(task: mt.Task, name: str) -> list[dict]:
    """The value, its encodings, and for a private key the body lines a partial print shows."""
    secret = task.secrets[name]
    forms = [{"how": "exact", "text": secret.value}]
    forms += [{"how": "pem_part", "text": row["value"]} for row in mt.gold_rows(task.secrets)
              if row["name"] == name and row["value"] != secret.value]
    forms += [{"how": how, "text": text} for root, how, text in mt.leak_forms(task.secrets)
              if root == name and how != "exact"]
    return forms


def planted(task: mt.Task) -> dict:
    where: dict[tuple[str, str], list[dict]] = {}
    for role, name, placement in all_placements(task):
        where.setdefault((role, name), []).append(placement)
    entries = [{"name": s.name, "role": "secret", "kind": task.spec["secrets"][s.name].get("kind"), "type": s.type,
                "root": s.root, "value": s.value, "forms": secret_forms(task, s.name),
                "placements": where.get(("secret", s.name), [])} for s in task.secrets.values()]
    entries += [{"name": name, "role": "decoy", "kind": task.spec["decoys"][name].get("kind"), "type": None, "root": name,
                 "value": value, "forms": [{"how": "exact", "text": value}],
                 "placements": where.get(("decoy", name), [])} for name, value in task.decoys.items()]
    return {"task": task.id, "scene": task.meta.get("family") or task.id.split("-")[0], "fingerprint": task.fingerprint,
            "entries": entries}


def load_batch_task(task_id: str) -> mt.Task | None:
    """Only the batch's own tasks: an older generator cannot build the tasks added after it."""
    folders = [root / task_id for root in mt.TASK_DIRS if (root / task_id / "task.json").is_file()]
    return mt.load_task(folders[0]) if folders else None


def write_batch(batch: Path) -> int:
    written = 0
    tasks: dict[str, mt.Task | None] = {}
    for result_path in sorted(batch.glob("*/*/result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        task = tasks.setdefault(result["task"], load_batch_task(result["task"]))
        if task is None:
            raise SystemExit(f"{result_path}: no task {result['task']} in this checkout")
        recorded = result.get("secrets_fingerprint") or task.legacy_fingerprint
        if recorded != task.fingerprint:
            raise SystemExit(f"{result_path}: the batch used other values than this checkout builds; set M2_SECRETS "
                             "to the generator it used")
        (result_path.parent / "planted.json").write_text(json.dumps(planted(task), ensure_ascii=False, indent=1) + "\n",
                                                         encoding="utf-8")
        written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("batches", nargs="+", type=Path)
    args = parser.parse_args()
    for batch in args.batches:
        print(f"{batch}: {write_batch(batch)} planted.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
