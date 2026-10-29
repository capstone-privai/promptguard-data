"""One process of the detection evaluation, started by runner.py.

  validate  check a sessions/gold pair with the scorer's validator and report each session's scored item count
  run       evaluate a range of sessions with a PromptGuard checkout and write the dashboard's counts for it

Each shard is its own process: a process can import one checkout's detector package only
(evaluation.adapters.system_root.load_worker), and the shards of a big dataset run side by side. The output file is
JSON (see collect.Collector.payload); exit codes follow evaluate.py: 1 invalid dataset, 2 scoring failed, 3 setup.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.taxonomy import CHANNELS, group_of  # noqa: E402  (importing pipeline puts metric-detection/ on sys.path)
from pipeline.collect import Collector  # noqa: E402

from evaluation.adapters.system_root import SystemRootError, load_worker  # noqa: E402
from evaluation.dataset.io import gold_from_record, iter_records  # noqa: E402
from evaluation.dataset.schema import Item, Session  # noqa: E402
from evaluation.dataset.validate import validate_dataset  # noqa: E402
from evaluation.run import ScoringError, check_use, evaluate_sessions  # noqa: E402

EXIT_DATASET, EXIT_SCORING, EXIT_CONFIG = 1, 2, 3
USE = "rule_eval"  # PromptGuard's worker runs CredSweeper without ML


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)


def load_range(sessions_path: Path, gold_path: Path, low: int, high: int) -> list[Session]:
    """Sessions low..high-1 in file order (blank lines skipped, as the scorer's loader does) with their gold."""
    gold: dict[str, list] = {}
    for _number, line in iter_records(gold_path):
        session_id, span = gold_from_record(json.loads(line))
        gold.setdefault(session_id, []).append(span)
    sessions = []
    for index, (_number, line) in enumerate(iter_records(sessions_path)):
        if index >= high:
            break
        if index < low:
            continue
        record = json.loads(line)
        items = [Item(item["item_id"], item["turn_id"], item["channel"], item["text"]) for item in record["items"]]
        sessions.append(Session(record["session_id"], items, gold.get(record["session_id"], []),
                                dict(record.get("meta") or {})))
    return sessions


def cmd_validate(args: argparse.Namespace) -> int:
    issues = validate_dataset(args.sessions, args.gold)
    weights = []
    if not issues:
        sessions = load_range(Path(args.sessions), Path(args.gold), 0, sys.maxsize)
        issues = check_use(sessions, args.use)
        weights = [sum(1 for item in session.items if item.channel in CHANNELS) for session in sessions]
    write_json(Path(args.out), {"issues": [str(issue) for issue in issues[:20]], "issue_count": len(issues),
                                "weights": weights})
    return EXIT_DATASET if issues else 0


def cmd_run(args: argparse.Namespace) -> int:
    if not args.gitleaks_cache:
        return evaluate_range(args)
    from pipeline.gitleaks_cache import install

    cache = install(Path(args.gitleaks_cache))
    try:
        return evaluate_range(args)
    finally:
        cache.close()
        print(f"gitleaks cache: {cache.hits} hits, {cache.misses} runs", file=sys.stderr)


def evaluate_range(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    low, high = (int(part) for part in args.lines.split(":"))
    sessions = load_range(Path(args.sessions), Path(args.gold), low, high)
    try:
        from evaluation.adapters.promptguard_adapter import PromptGuardAdapter

        adapter = PromptGuardAdapter(load_worker(args.system_root))
    except (SystemRootError, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        result = evaluate_sessions(sessions, adapter)
    except ScoringError as exc:
        print(f"scoring failed: {exc}", file=sys.stderr)
        return EXIT_SCORING

    collector = Collector(args.dataset, group_of(args.dataset))
    lookup = {(session.session_id, item.item_id): (session, item) for session in sessions for item in session.items}
    for score in result.scores:
        session, item = lookup[(score.session_id, score.item_id)]
        collector.add(session, item, score, result.outputs[(score.session_id, score.item_id)])
    payload = collector.payload()
    payload.update(counts=result.metrics["counts"], lines_total=result.metrics["lines_total"], system=result.system,
                   sessions=len(sessions), item_count=result.metrics["items"], seconds=time.perf_counter() - started)
    write_json(Path(args.out), payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    run = commands.add_parser("run")
    for command in (validate, run):
        command.add_argument("--sessions", required=True)
        command.add_argument("--gold", required=True)
        command.add_argument("--out", required=True)
    validate.add_argument("--use", choices=("rule_eval", "ml_eval"), default=USE)
    run.add_argument("--dataset", required=True, help="sessions file stem, e.g. sessions_from_CredData")
    run.add_argument("--lines", required=True, help="session range low:high in file order")
    run.add_argument("--system-root", required=True, help="PromptGuard checkout (src/detector, the mod's register.mjs)")
    run.add_argument("--gitleaks-cache", help="SQLite file caching gitleaks runs across shards and commits")
    args = parser.parse_args(argv)
    return cmd_validate(args) if args.command == "validate" else cmd_run(args)


if __name__ == "__main__":
    def stop(_signal, _frame):
        raise SystemExit(130)
    signal.signal(signal.SIGTERM, stop)
    raise SystemExit(main())
