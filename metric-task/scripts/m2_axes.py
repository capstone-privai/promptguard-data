#!/usr/bin/env python3
"""What the tasks are about, counted in scenes. Reads task definitions and task_axes.toml, never starts Claude.

A family's tasks change one axis of one scene, so 135 tasks are far fewer independent contexts. Minimum counts for the
trajectory evaluation set are per scene.

    python3 metric-task/scripts/m2_axes.py            # tables; exit 1 if a scene has no label or a label has no scene
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2_inventory as inventory  # noqa: E402
import m2_tasks as mt  # noqa: E402

AXES_FILE = mt.REPO_ROOT / "metric-task" / "task_axes.toml"
WORK = ("feature", "bugfix", "refactor", "test", "migration", "incident", "deploy", "data", "review", "docs", "security",
        "lookup")
CREDENTIAL = ("central", "incidental")
MIN_SCENES_PER_WORK = 5


def scene_of(task: mt.Task) -> str:
    return task.meta.get("family") or task.id.split("-")[0]


def load_labels(path: Path = AXES_FILE) -> dict[str, dict]:
    with path.open("rb") as f:
        return tomllib.load(f)["scenes"]


def problems(tasks: list[mt.Task], labels: dict[str, dict]) -> list[str]:
    scenes = {scene_of(t) for t in tasks}
    out = [f"scene {s} has no label in {AXES_FILE.name}" for s in sorted(scenes - set(labels))]
    out += [f"label {s} has no task" for s in sorted(set(labels) - scenes)]
    for scene, label in sorted(labels.items()):
        if label.get("work") not in WORK:
            out.append(f"scene {scene}: unknown work {label.get('work')!r}")
        if label.get("credential") not in CREDENTIAL:
            out.append(f"scene {scene}: unknown credential {label.get('credential')!r}")
    return out


def census(tasks: list[mt.Task], labels: dict[str, dict]) -> dict:
    """{axis: {value: {"tasks": n, "scenes": n}}}, listing every known value so an empty one shows as a gap."""
    found: dict[str, dict[str, list]] = {
        "work": {w: [] for w in WORK}, "credential": {c: [] for c in CREDENTIAL}, "project": {}}
    for task in tasks:
        scene = scene_of(task)
        found["work"][labels[scene]["work"]].append(scene)
        found["credential"][labels[scene]["credential"]].append(scene)
        found["project"].setdefault(inventory.project(task), []).append(scene)
    return {axis: {value: {"tasks": len(scenes), "scenes": len(set(scenes))} for value, scenes in values.items()}
            for axis, values in found.items()}


def report(result: dict) -> str:
    lines = []
    for axis, values in result.items():
        lines += [f"\n{axis}", f"  {'value':12s} {'scenes':>6s} {'tasks':>6s}"]
        for value, count in sorted(values.items(), key=lambda kv: (-kv[1]["scenes"], kv[0])):
            short = "  below minimum" if axis == "work" and count["scenes"] < MIN_SCENES_PER_WORK else ""
            lines.append(f"  {value:12s} {count['scenes']:6d} {count['tasks']:6d}{short}")
    return "\n".join(lines).lstrip()


def cross(tasks: list[mt.Task], labels: dict[str, dict]) -> dict[str, dict[str, int]]:
    """Scenes of each work kind where the credential is only nearby: the sessions closest to everyday development."""
    scenes = defaultdict(set)
    for task in tasks:
        scene = scene_of(task)
        scenes[labels[scene]["work"], labels[scene]["credential"]].add(scene)
    return {w: {c: len(scenes[w, c]) for c in CREDENTIAL} for w in WORK}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks", nargs="*", default=["all"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    tasks, labels = mt.load_tasks(args.tasks), load_labels()
    found = problems(tasks, labels) if args.tasks == ["all"] else []
    for problem in found:
        print(f"BAD {problem}", file=sys.stderr)
    if found:
        return 1
    result = census(tasks, labels)
    if args.json:
        print(json.dumps({**result, "work_by_credential": cross(tasks, labels)}, ensure_ascii=False, indent=2))
    else:
        print(f"{len(tasks)} tasks, {len({scene_of(t) for t in tasks})} scenes\n")
        print(report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
