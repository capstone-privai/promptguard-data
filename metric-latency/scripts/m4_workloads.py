"""What the latency evaluator sends to a detector: the calls of each workload, in order.

A workload is a list of sessions; a session is what one detector client sends in one Claude Code session.
Three sources:

  synth     generated text of fixed sizes and batch sizes, with and without secret-like lines (no state)
  guard     the Final Guard's calls, replayed from metric-task API captures (api_requests.jsonl.xz): every
            POST /v1/messages* body is cut into its string leaves, and only leaves the Guard has not yet
            seen clean go to the detector, deduplicated, in batches of GUARD_BATCH (see guard_session)
  recorded  the Native Mod's calls exactly as a metric-task run recorded them (detector_calls.jsonl.xz, written
            by metric-task/scripts/detector_capture.py)

Nothing here imports the system or metric-task. The guard replay follows the Guard's documented cache rules
(src/guard/lib.cjs in promptguard-claude-demoV0: string leaves only, clean verdicts cached per process,
leaves with a finding never cached, at most 256 uncached leaves per call, stop at the first batch with a
finding). Those constants are the only system knowledge in this file.
"""
from __future__ import annotations

import json
import lzma
import random
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

GUARD_BATCH = 256
CAPTURE_FILE = "api_requests.jsonl.xz"
RECORDED_FILE = "detector_calls.jsonl.xz"

SYNTH_SIZES = (128, 1024, 4096, 16384, 65536, 262144)
SYNTH_BATCHES = (1, 4, 16, 64, 256)
SYNTH_BATCH_ITEM = 1024


@dataclass
class Call:
    items: list[dict]  # {"id", "text", "source"}, the request body the detector gets
    workload: str  # a label to group by, e.g. "synth/plain/size=1024/batch=1"
    meta: dict = field(default_factory=dict)


@dataclass
class Session:
    source: str  # synth | guard | recorded
    name: str
    calls: Iterator[Call] | None = None  # fixed calls (synth, recorded)
    requests: list[list[str]] | None = None  # guard: the string leaves of each request, in order


# ---- synth ------------------------------------------------------------------------------------------------

_LOG = ("{ts} INFO api request_id={hex12} method=GET path=/v1/orders/{n} status=200 duration_ms={n2}",
        "{ts} WARN worker retry attempt={d} queue=billing-events backoff_ms={n2}",
        "{ts} ERROR db connection refused host=db-{d}.internal port=5432 code=E_CONN",
        "    at OrderService.load (src/orders/service.ts:{n2}:{d})",
        "def handle_{word}(event, context):",
        "    return process(event['body'], timeout={d}0)",
        "timeout_seconds = {n2}",
        "  replicas: {d}",
        "SELECT id, status FROM orders WHERE customer_id = {n} LIMIT 50;")
_SECRET = ("DB_PASSWORD={alnum16}",
           "api_key: \"{alnum32}\"",
           "export GITHUB_TOKEN=ghp_{alnum36}",
           "AWS_ACCESS_KEY_ID=AKIA{upper16}",
           "Authorization: Bearer {alnum40}")


def _fill(template: str, rng: random.Random) -> str:
    alnum = string.ascii_letters + string.digits
    pick = lambda chars, n: "".join(rng.choice(chars) for _ in range(n))  # noqa: E731
    return template.format(
        ts=f"2026-10-11T{rng.randrange(24):02d}:{rng.randrange(60):02d}:{rng.randrange(60):02d}Z",
        hex12=pick("0123456789abcdef", 12), n=rng.randrange(10_000, 99_999), n2=rng.randrange(10, 999),
        d=rng.randrange(1, 9), word=rng.choice(("orders", "refund", "invoice", "webhook")),
        alnum16=pick(alnum, 16), alnum32=pick(alnum, 32), alnum36=pick(alnum, 36), alnum40=pick(alnum, 40),
        upper16=pick(string.ascii_uppercase + "234567", 16))


def synth_text(size: int, kind: str, seed: str) -> str:
    """Exactly `size` characters of log, code and config lines, ending in a newline. kind "secrets" puts a
    secret-like line about every 20 lines (at least one); "plain" has none. The last line is cut from a plain
    line, so no secret is ever cut. Deterministic for the same arguments."""
    rng = random.Random(f"{kind}:{size}:{seed}")
    lines, length, count = [], 0, 0
    while True:
        secret = kind == "secrets" and (count % 20 == 3 or (count == 0 and size < 400))
        line = _fill(rng.choice(_SECRET if secret else _LOG), rng)
        if length + len(line) + 1 >= size:
            filler = " ".join(_fill(rng.choice(_LOG), rng) for _ in range(4))
            lines.append(filler[:size - length - 1])
            return "\n".join(lines) + "\n"
        lines.append(line)
        length += len(line) + 1
        count += 1


def synth_sessions(sizes=SYNTH_SIZES, batches=SYNTH_BATCHES, kinds=("plain", "secrets")) -> list[Session]:
    """Size sweep (one text per call) and batch sweep (SYNTH_BATCH_ITEM-character texts), per kind."""
    def calls() -> Iterator[Call]:
        for kind in kinds:
            for size in sizes:
                yield Call([{"id": 0, "text": synth_text(size, kind, "0"), "source": "synth"}],
                           f"synth/{kind}/size={size}/batch=1", {"kind": kind, "size": size, "batch": 1})
            for batch in batches:
                if batch == 1:
                    continue  # the size sweep already has it
                items = [{"id": i, "text": synth_text(SYNTH_BATCH_ITEM, kind, str(i)), "source": "synth"}
                         for i in range(batch)]
                yield Call(items, f"synth/{kind}/size={SYNTH_BATCH_ITEM}/batch={batch}",
                           {"kind": kind, "size": SYNTH_BATCH_ITEM, "batch": batch})
    return [Session("synth", "synth", calls=calls())]


# ---- guard replay ------------------------------------------------------------------------------------------

def string_leaves(value) -> list[str]:
    """Every string value (not object keys) in document order, as the Guard's collectStringLeaves."""
    out, stack = [], [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, list):
            stack.extend(reversed(item))
        elif isinstance(item, dict):
            stack.extend(reversed(list(item.values())))
    return out


def _read_jsonl_xz(path: Path) -> list[dict]:
    with lzma.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _find(paths: list[str], filename: str) -> list[Path]:
    found = []
    for raw in paths:
        path = Path(raw)
        found += [path] if path.is_file() else sorted(path.rglob(filename))
    if not found:
        raise SystemExit(f"no {filename} under {paths}")
    return found


def _session_name(path: Path) -> str:
    return "/".join(path.parts[-3:-1])  # <task>/<condition>-r<n>


def guard_sessions(paths: list[str]) -> list[Session]:
    """One session per capture file: the bodies of the requests the Guard would scan (POST /v1/messages and
    /v1/messages/count_tokens), cut into string leaves."""
    sessions = []
    for path in _find(paths, CAPTURE_FILE):
        requests = []
        for record in _read_jsonl_xz(path):
            if record.get("method") != "POST" or not str(record.get("path", "")).split("?")[0].startswith("/v1/messages"):
                continue
            try:
                body = json.loads(record.get("body") or "")
            except ValueError:
                continue  # the Guard rejects a body that is not JSON before any scan
            requests.append(string_leaves(body))
        sessions.append(Session("guard", _session_name(path), requests=requests))
    return sessions


def guard_session(requests: list[list[str]],
                  scan: Callable[[list[dict], dict], list[int] | None]) -> Iterator[dict]:
    """Replays the Guard's scanLeaves over one session. `scan(items, meta)` makes one detector call and returns
    the finding count of each item, or None when the call failed (the Guard then blocks the request: it fails
    closed). Yields one summary per request."""
    clean: set[str] = set()
    for index, leaves in enumerate(requests):
        pending: dict[str, None] = {}
        for text in leaves:
            if text not in clean and text not in pending:
                pending[text] = None
        unique = list(pending)
        calls, findings, failed = 0, 0, False
        for start in range(0, len(unique), GUARD_BATCH):
            batch = unique[start:start + GUARD_BATCH]
            items = [{"id": i, "text": text, "source": "outbound"} for i, text in enumerate(batch)]
            counts = scan(items, {"request": index, "batch": start // GUARD_BATCH})
            calls += 1
            if counts is None:
                failed = True
                break
            for text, count in zip(batch, counts):
                if count == 0:
                    clean.add(text)
                findings += count
            if findings:
                break  # the request is blocked; the Guard does not scan the rest
        yield {"request": index, "leaves": len(leaves), "unique": len(unique), "calls": calls,
               "findings": findings, "failed": failed}


# ---- recorded ----------------------------------------------------------------------------------------------

def recorded_sessions(paths: list[str]) -> list[Session]:
    """One session per recorded metric-task run: its /scan-batch calls in the order the Mod made them."""
    sessions = []
    for path in _find(paths, RECORDED_FILE):
        records = sorted((r for r in _read_jsonl_xz(path) if r.get("path") == "/scan-batch" and isinstance(r.get("items"), list)),
                         key=lambda r: r.get("seq", 0))

        def calls(records=records) -> Iterator[Call]:
            for seq, record in enumerate(records):
                sources = sorted({str(item.get("source", "unknown")) for item in record["items"]})
                yield Call(record["items"], "recorded/" + "+".join(sources), {"seq": seq})
        sessions.append(Session("recorded", _session_name(path), calls=calls()))
    return sessions
