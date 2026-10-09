"""Command line entry point: `python metric-1/scripts/evaluate.py validate|run ...`
(or `python -m evaluation ...` from metric-1/).

Exit codes: 0 ok, 1 invalid dataset, 2 edit verification failed, 3 configuration error.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from evaluation.adapters.base import SystemUnderTest
from evaluation.adapters.promptguard_adapter import CHANNEL_MAP
from evaluation.adapters.system_root import SystemRootError, load_worker, resolve_system_root
from evaluation.dataset.io import gold_path_for, load_sessions
from evaluation.dataset.schema import CHANNELS, USES
from evaluation.dataset.validate import validate_dataset
from evaluation.report.meta import build_run_meta
from evaluation.report.write import create_run_dir, fmt, write_run
from evaluation.run import DatasetInvalidError, ScoringError, evaluate_sessions, load_dataset

EXIT_OK = 0
EXIT_DATASET = 1
EXIT_SCORING = 2
EXIT_CONFIG = 3

SYSTEMS = ("promptguard", "credsweeper", "gitleaks", "oracle", "identity")
DEFAULT_SESSIONS = Path(__file__).resolve().parents[1] / "data_test" / "sessions.jsonl"

AdapterFactory = Callable[[], SystemUnderTest]


class ConfigError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # argparse would exit 2, which means a scoring failure here
        raise ConfigError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="metric-1/scripts/evaluate.py", description="PromptGuard metric 1 evaluation")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    validate = commands.add_parser("validate", help="check a dataset's format")
    run = commands.add_parser("run", help="run a system over a dataset, score it and write a run folder")
    for command in (validate, run):
        command.add_argument("--sessions", default=str(DEFAULT_SESSIONS),
                             help="sessions file (default: metric-1/data_test/sessions.jsonl)")
        command.add_argument("--gold", help="gold file (default: data_test/sessions*.jsonl → data_answer/gold*.jsonl)")
    run.add_argument("--system", required=True, choices=SYSTEMS)
    run.add_argument("--system-root", help="promptguard-claude-demoV0 checkout for --system promptguard "
                                           "(default: $PROMPTGUARD_CLAUDE_ROOT, else ../promptguard-claude-demoV0)")
    run.add_argument("--use", choices=USES, help="purpose every session's meta.allowed_use must include "
                                                 "(default: ml_eval for credsweeper --ml on, else rule_eval)")
    run.add_argument("--ml", choices=("on", "off"), help="CredSweeper ML validation (credsweeper only; default: off)")
    run.add_argument("--channels", help="comma-separated channels to scan, or 'all' (credsweeper only; "
                                        f"default: {','.join(CHANNEL_MAP)}, the channels PromptGuard processes)")
    run.add_argument("--findings", help="findings file from metric-1/scripts/run_gitleaks.py (gitleaks only, required)")
    run.add_argument("--out", default="runs", help="parent folder for run folders (default: runs)")
    run.add_argument("--debug", action="store_true", help="also write debug/ with raw candidates (contains secrets)")
    return parser


def summary_line(metrics: dict[str, Any]) -> str:
    return (
        f"recall={fmt(metrics['recall'])} precision={fmt(metrics['precision'])} f2={fmt(metrics['f2'])} "
        f"fp_per_1k_lines={fmt(metrics['fp_per_1k_lines'], 2)} gold={metrics['counts']['gold_total']} "
        f"density_per_1k_lines={fmt(metrics['density_per_1k_lines'], 2)}"
    )


def resolve_gold(args: argparse.Namespace) -> str:
    return args.gold or str(gold_path_for(args.sessions))


def default_use(args: argparse.Namespace) -> str:
    if args.use is not None:
        return args.use
    if args.system == "credsweeper" and args.ml == "on":
        return "ml_eval"
    return "rule_eval"  # PromptGuard's worker runs CredSweeper without ML


def adapter_factory(args: argparse.Namespace) -> tuple[AdapterFactory, str, Path | None]:
    """Return an adapter factory, the run folder label and the system checkout (if any)."""
    if args.system != "promptguard" and args.system_root:
        raise ConfigError("--system-root applies to --system promptguard only")
    if args.system != "credsweeper" and (args.ml or args.channels):
        raise ConfigError("--ml and --channels apply to --system credsweeper only")
    if (args.system == "gitleaks") != bool(args.findings):
        raise ConfigError("--system gitleaks needs --findings (from metric-1/scripts/run_gitleaks.py), "
                          "and --findings applies to --system gitleaks only")
    if args.system == "promptguard":
        from evaluation.adapters.promptguard_adapter import PromptGuardAdapter

        try:
            root = resolve_system_root(args.system_root)
            worker = load_worker(root)
        except SystemRootError as exc:
            raise ConfigError(str(exc)) from exc
        return (lambda: PromptGuardAdapter(worker, debug=args.debug)), "promptguard", root
    if args.system == "credsweeper":
        ml = args.ml == "on"
        label = f"credsweeper_ml-{'on' if ml else 'off'}"
        channels = (tuple(CHANNEL_MAP) if not args.channels else
                    CHANNELS if args.channels == "all" else tuple(dict.fromkeys(args.channels.split(","))))
        if unknown := [channel for channel in channels if channel not in CHANNELS]:
            raise ConfigError(f"unknown channel(s) {unknown}; expected 'all' or some of {list(CHANNELS)}")
        if args.channels:
            suffix = "all" if set(channels) == set(CHANNELS) else "+".join(channels)
            label = f"{label}_{suffix}"

        def make_credsweeper() -> SystemUnderTest:
            # Check the dataset's purpose before loading the detector and its ML dependencies.
            from evaluation.adapters.credsweeper_adapter import CredSweeperAdapter

            return CredSweeperAdapter(ml=ml, channels=channels)

        return make_credsweeper, label, None
    if args.system == "gitleaks":
        from evaluation.adapters.gitleaks_adapter import GitleaksAdapter

        return (lambda: GitleaksAdapter(args.findings, args.sessions)), "gitleaks", None
    if args.system == "oracle":
        from evaluation.adapters.reference import OracleAdapter

        return (lambda: OracleAdapter()), "oracle", None
    if args.system == "identity":
        from evaluation.adapters.reference import IdentityAdapter

        return (lambda: IdentityAdapter()), "identity", None
    raise ConfigError(f"unknown system {args.system!r}")


def _validate(sessions_path: str, gold_path: str, out: TextIO) -> int:
    issues = validate_dataset(sessions_path, gold_path)
    if issues:
        for issue in issues:
            print(issue, file=out)
        print(f"{len(issues)} issue(s) found", file=out)
        return EXIT_DATASET
    sessions = load_sessions(sessions_path, gold_path)
    items = sum(len(session.items) for session in sessions)
    gold = sum(len(session.gold) for session in sessions)
    print(f"OK: {len(sessions)} sessions, {items} items, {gold} gold spans", file=out)
    return EXIT_OK


def execute_run(
    sessions_path: str,
    gold_path: str,
    make_adapter: AdapterFactory,
    *,
    label: str = "run",
    use: str = "rule_eval",
    out_root: str | Path = "runs",
    debug: bool = False,
    system_root: Path | None = None,
    out: TextIO | None = None,
) -> int:
    """Validate, run, score and write. Adapters are injected so tests can reach every exit path."""
    out = out or sys.stdout
    started_at = datetime.now()
    try:
        sessions = load_dataset(sessions_path, gold_path, use)
    except DatasetInvalidError as exc:
        for issue in exc.issues:
            print(issue, file=out)
        print(f"dataset invalid: {len(exc.issues)} issue(s); nothing was run", file=out)
        return EXIT_DATASET

    try:
        adapter = make_adapter()
    except (ConfigError, ValueError) as exc:
        print(f"configuration error: {exc}", file=out)
        return EXIT_CONFIG
    try:
        result = evaluate_sessions(sessions, adapter)
    except ScoringError as exc:
        print(f"scoring failed: {exc}", file=out)
        print("no results were written", file=out)
        return EXIT_SCORING

    meta = build_run_meta(started_at=started_at, system=result.system, sessions_path=sessions_path,
                          gold_path=gold_path, sessions=sessions, use=use, debug=debug, system_root=system_root)
    run_dir = create_run_dir(out_root, label, started_at)
    write_run(run_dir, meta=meta, result=result, debug=debug)
    print(f"results: {run_dir}", file=out)
    print(summary_line(result.metrics), file=out)
    if debug:
        print("warning: debug/ contains raw text including secrets; do not share or commit it", file=out)
    return EXIT_OK


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    out = out or sys.stdout
    try:
        args = build_parser().parse_args(argv)
        gold_path = resolve_gold(args)
        if args.command == "validate":
            return _validate(args.sessions, gold_path, out)
        make_adapter, label, system_root = adapter_factory(args)
    except (ConfigError, ValueError) as exc:
        print(f"configuration error: {exc}", file=out)
        return EXIT_CONFIG
    return execute_run(args.sessions, gold_path, make_adapter, label=label, use=default_use(args), out_root=args.out,
                       debug=args.debug, system_root=system_root, out=out)
