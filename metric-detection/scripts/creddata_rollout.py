"""Run a small balanced collection pilot and annotate known values in captured API request text.

No task-success grader. API or subscription authentication is selected explicitly; no silent fallback.
The existing capture proxy and context labeling rules are reused without changing benchmark files.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote
import uuid

import creddata_tasks as T
import convert_trajectory as C
import value_gen

sys.path.insert(0, str(T.ROOT / "metric-task/scripts"))
from api_capture import CaptureProxy  # noqa: E402

WORK_BASE = Path(os.environ.get("CREDDATA_WORK_BASE", Path.home() / "workspaces"))


def api_environment(env_file: Path | None = None) -> dict:
    env = dict(os.environ)
    if env_file is not None:
        for line in env_file.read_text().splitlines():
            line = line.strip().removeprefix("export ")
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() not in {"ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"}:
                continue
            parsed = shlex.split(value, comments=True)
            if len(parsed) != 1:
                raise ValueError("API environment file needs one literal value per variable")
            env[name.strip()] = parsed[0]
    if not env.get("ANTHROPIC_API_KEY"):
        raise ValueError("ANTHROPIC_API_KEY is not configured; set it or pass --env-file. Subscription auth is not used.")
    for name in list(env):
        if name in {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN"} or \
                name.startswith("CLAUDE_CODE_MESSAGING_"):
            env.pop(name)
    return env


def subscription_environment() -> dict:
    """Use the account already logged into Claude Code, without ambient API/provider overrides."""
    env = dict(os.environ)
    for name in list(env):
        if name in {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN",
                    "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_SIMPLE", "CLAUDE_CODE_USE_BEDROCK",
                    "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"} or name.startswith("CLAUDE_CODE_MESSAGING_"):
            env.pop(name)
    result = subprocess.run(["claude", "auth", "status"], env=env, capture_output=True, text=True, check=True)
    auth = json.loads(result.stdout)
    if not auth.get("loggedIn") or auth.get("authMethod") != "claude.ai":
        raise ValueError("subscription mode needs an existing Claude account login")
    return env


class ModelGuardConnection:
    """Reject a non-Haiku model before forwarding any request upstream."""

    def __init__(self, connection):
        self.connection = connection

    def request(self, method, url, body=None, headers=None):
        try:
            payload = json.loads(body) if body else {}
        except (ValueError, UnicodeError):
            payload = {}
        model = payload.get("model") if isinstance(payload, dict) else None
        if model is not None and (not isinstance(model, str) or "haiku" not in model.lower()):
            raise ValueError("haiku_only: non-Haiku request blocked before forwarding")
        return self.connection.request(method, url, body=body, headers=headers or {})

    def getresponse(self):
        return self.connection.getresponse()

    def close(self):
        return self.connection.close()


class HaikuOnlyProxy(CaptureProxy):
    def connection(self):
        return ModelGuardConnection(super().connection())


LINE_NUMBER = (re.compile(r"[ \t]*(\d+)(?:\t|\u2192)"), re.compile(r"(\d+)[:-]"))


def strip_line_numbers(text: str) -> tuple[str, list[int] | None]:
    """A tool output whose every line carries an increasing line number (cat -n or the Read tool: right-aligned number
    and tab; grep -n: N: or N-) without the numbers, and the original offset of each kept character (end included).
    Other text is returned unchanged with None."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) < 2:
        return text, None
    for pattern in LINE_NUMBER:
        matches = [pattern.match(line) for line in lines]
        if all(matches) and all(int(a[1]) < int(b[1]) for a, b in zip(matches, matches[1:])):
            break
    else:
        return text, None
    kept, offsets, cursor = [], [], 0
    for line, m in zip(lines, matches):
        kept.append(line[m.end():])
        offsets.extend(range(cursor + m.end(), cursor + len(line) + 1))  # the line and its newline
        cursor += len(line) + 1
    plain = "\n".join(kept) + ("\n" if text.endswith("\n") else "")
    offsets = offsets[:len(plain)]
    offsets.append(offsets[-1] + 1 if offsets else 0)
    return plain, offsets


def whole_file_entries(task: dict, registry: dict) -> list[dict]:
    """Known values of a whole-file task (catalog v3): the span type is the CredData category. Key blocks and JWK
    fragments are found by their exact rendered text (structured), single values by the usual forms and rules."""
    import creddata_fullfile as F
    entries = []
    for name, value in registry["values"].items():
        slot = task["slots"][name]
        occurrences = [o for o in task["occurrences"] if o["secret_id"] == name]
        if slot["structure"]:
            forms = {value: "exact"}
            for occurrence in occurrences:
                forms.setdefault(F.encode(value, occurrence, slot), "layout")
            entries.append({"name": name, "root": name, "kind": "category", "role": "secret", "value": value,
                            "type": slot["type"], "structured": True,
                            "forms": [{"text": t, "how": how} for t, how in forms.items()]})
            continue
        forms = {value: "exact"}
        if value:
            forms.setdefault(quote(value, safe=""), "urlencoded")
            forms.setdefault(base64.b64encode(value.encode()).decode(), "base64")
        codecs = {"json", "python_single", "python_double"} | {
            o["codec"] for o in occurrences if o["codec"] not in ("raw", "pem", "jwk")}
        for codec in sorted(codecs):
            try:
                encoded = T.encode_fragment(value, codec)
            except ValueError:
                continue
            forms.setdefault(encoded, codec)
            forms.setdefault(json.dumps(encoded, ensure_ascii=False)[1:-1], "json_of_" + codec)
        entries.append({"name": name, "root": name, "kind": "category", "role": "secret", "value": value,
                        "type": slot["type"], "forms": [{"text": t, "how": how} for t, how in forms.items() if t]})
    return entries


def structured_spans(text: str, entries: list[dict]) -> list[dict]:
    """Every exact occurrence of a key block or JWK fragment form: gold wherever it is, like a PEM block."""
    spans = []
    for entry in entries:
        for form in entry["forms"]:
            at = text.find(form["text"])
            while at >= 0:
                spans.append({"entry": entry["name"], "role": "secret", "service": entry["kind"],
                              "value_class": "distinct", "value_sha256": C.digest(entry["value"]),
                              "start": at, "end": at + len(form["text"]), "rule": "known_structured_value",
                              "how": form["how"], "type": entry["type"], "kind": "known_structured_value"})
                at = text.find(form["text"], at + 1)
    return spans


ARMOR = re.compile(r"-----(BEGIN|END) [A-Z0-9 ]+-----")
GAP = 200  # characters allowed between two pieces of one key: line numbers, quotes, escapes, "$", indentation


def key_streams(value: str) -> list[str]:
    """The secret character streams of a structured value: the base64 body of a PEM block as one stream whatever its
    line wrapping, or each long token of another fragment (the field values of a JWK)."""
    if value.startswith("-----BEGIN"):
        body = [l.strip() for l in ARMOR.sub("\n", value).split("\n")]
        return ["".join(l for l in body if l and ":" not in l and " " not in l)]
    return re.findall(r"[A-Za-z0-9+/=_-]{16,}", value)


def stream_spans(text: str, entries: list[dict]) -> list[dict]:
    """Key material shown in a form the exact search cannot know: other line prefixes or suffixes, escapes, quotes,
    re-wrapping, or only part of the key. Tokens of the text are aligned to the key's character stream; consecutive
    aligned tokens at most GAP apart are one span (the junk between them included), extended to the armor lines when
    the stream starts or ends there. A partial key is still key material and is gold; `coverage` records how much."""
    spans = []
    for entry in entries:
        for stream in key_streams(entry["value"]):
            if len(stream) < 16:
                continue
            url = "-" in stream or "_" in stream
            token = re.compile(r"\\+[nrt]|([A-Za-z0-9+/=_-]+)" if url else r"\\+[nrt]|([A-Za-z0-9+/=]+)")
            tokens = [(m.start(1), m.end(1), m[1]) for m in token.finditer(text) if m[1]]
            index = 0
            while index < len(tokens):
                start, end, word = tokens[index]
                at = stream.find(word) if len(word) >= 16 else -1
                index += 1
                if at < 0:
                    continue
                first, position, covered = at, at + len(word), len(word)
                while index < len(tokens) and tokens[index][0] - end <= GAP:
                    _, next_end, word = tokens[index]
                    if stream.startswith(word, position) and (len(word) >= 8 or position + len(word) == len(stream)):
                        hit = position
                    else:
                        hit = stream.find(word, position) if len(word) >= 16 else -1
                    if hit < 0:
                        if len(word) >= 16:
                            break  # another long token: not this key any more
                        index += 1
                        continue
                    end, position, covered = next_end, hit + len(word), covered + len(word)
                    index += 1
                if first == 0:
                    armor = [m for m in ARMOR.finditer(text, max(0, start - GAP), start) if m[1] == "BEGIN"]
                    start = armor[-1].start() if armor else start
                if position == len(stream):
                    armor = ARMOR.search(text, end, end + GAP)
                    end = armor.end() if armor and armor[1] == "END" else end
                full = covered == len(stream)
                spans.append({"entry": entry["name"], "role": "secret", "service": entry["kind"], "value_class": "distinct",
                              "value_sha256": C.digest(entry["value"]), "start": start, "end": end,
                              "rule": "known_key_stream", "how": "stream" if full else "stream_partial",
                              "coverage": round(covered / len(stream), 3), "type": entry["type"],
                              "kind": "known_structured_value"})
    return spans


def label_whole_file_item(text: str, entries: list[dict], common: set[str], stats: Counter):
    """(gold, excluded, review) rows of one item of a whole-file task, in the item's own coordinates.

    A line-numbered tool output is labeled without its numbers and the spans are mapped back: a value that runs over
    several lines is one span from its first to its last character, the line-number prefixes inside it included."""
    plain, offsets = strip_line_numbers(text)
    single = [e for e in entries if not e.get("structured")]
    found, excluded = C.find_candidates(plain, single, common, set())
    merged = C.merge(found + structured_spans(plain, [e for e in entries if e.get("structured")]), stats)
    types = {e["name"]: e["type"] for e in entries}
    for span in merged:
        span["coarse_type"], span["type"] = span["type"], types[span["entry"]]
    review = C.to_review(plain, entries, merged + excluded)
    if offsets is not None:
        for row in merged + excluded + review:
            row["start"], row["end"] = offsets[row["start"]], offsets[row["end"] - 1] + 1
    extra = [s for s in stream_spans(text, [e for e in entries if e.get("structured")])
             if not C.overlaps(s["start"], s["end"], merged)]
    if extra:
        review = [r for r in review if not C.overlaps(r["start"], r["end"], extra)]
        merged = sorted(merged + extra, key=lambda r: r["start"])
    return merged, excluded, review


def entries_for(task: dict, registry: dict) -> list[dict]:
    if task.get("source_scope") == "whole_file":
        return whole_file_entries(task, registry)
    entries = []
    for name, value in registry["values"].items():
        slot = task["slots"][name]
        kind = slot["generator_kind"]
        forms = {value: "exact"}
        if value:
            forms.setdefault(quote(value, safe=""), "urlencoded")
            forms.setdefault(base64.b64encode(value.encode()).decode(), "base64")
        codecs = {"json", "python_single", "python_double"} | {
            a["codec"] for a in registry.get("source_annotations", []) if a["secret_id"] == name}
        for codec in sorted(codecs):
            encoded = T.encode_fragment(value, codec)
            forms.setdefault(encoded, codec)
            forms.setdefault(json.dumps(encoded, ensure_ascii=False)[1:-1], "json_of_" + codec)
        gold_type = value_gen.SECRET_KINDS[kind][0] if kind in value_gen.SECRET_KINDS else slot["type"]
        entry = {"name": name, "root": name, "kind": kind, "role": "secret", "value": value,
                 "type": gold_type, "forms": [{"text": text, "how": how} for text, how in forms.items() if text]}
        entries.append(entry)
        if kind == "basic_auth":
            try:
                decoded = base64.b64decode(value, validate=True).decode()
                user, separator, password = decoded.partition(":")
            except (ValueError, UnicodeError):
                separator = ""
            if separator and password:
                derived = {"name": name + "_decoded_password", "root": name, "kind": kind, "role": "secret",
                           "value": password, "type": "PASSWORD", "forms": [{"text": password, "how": "basic_decoded"}]}
                entries.append(derived)
    return entries


def label_items(task: dict, registry: dict, items: list[C.Item], session_id: str):
    entries = entries_for(task, registry)
    common = C.common_values(entries, [i.text for i in items])
    gold, labels, item_rows, stats = [], [], [], Counter()
    for item_id, item in enumerate(items):
        item_rows.append({"item_id": item_id, "turn_id": item.turn_id, "channel": item.channel, "text": item.text})
        if task.get("source_scope") == "whole_file":
            merged, excluded, review = label_whole_file_item(item.text, entries, common, stats)
        else:
            found, excluded = C.find_candidates(item.text, entries, common, set())
            merged = C.merge(found, stats)
        for span_id, span in enumerate(merged):
            start, end = span["start"], span["end"]
            if not 0 <= start < end <= len(item.text):
                raise ValueError("invalid derived trajectory span")
            gold.append({"session_id": session_id, "item_id": item_id, "span_id": span_id,
                         "span": {"start": start, "end": end, "type": span["type"]}})
            labels.append({"session_id": session_id, "item_id": item_id, "channel": item.channel,
                           "gold": True, **span})
            stats["gold_" + item.channel] += 1
        if task.get("source_scope") != "whole_file":
            review = C.to_review(item.text, entries, merged + excluded)
        for row in excluded:
            if not C.overlaps(row["start"], row["end"], merged):
                labels.append({"session_id": session_id, "item_id": item_id, "channel": item.channel,
                               "gold": False, "review": C.needs_review(row), **row})
        for row in review:
            labels.append({"session_id": session_id, "item_id": item_id, "channel": item.channel,
                           "gold": False, **row})
        stats["review_candidates"] += len(review) + sum(C.needs_review(row) for row in excluded)
    session = {"session_id": session_id, "items": item_rows, "meta": {
        "source": "creddata-derived-agent-pilot", "dataset_version": "creddata-pilot-v1", "origin": "recorded",
        "split": task["split"], "allowed_use": ["ml_train"], "task": task["task_id"], "family": task["family"],
        "group_id": task["component_id"], "source_repo_id": task["source_repo_id"],
        "source_session_id": task["source_session_id"], "source_item_id": task["source_item_id"],
        "source_origin": "external", "source_license": task["source_license"],
        "annotation_scope": "known generated values; unregistered and partial candidates require review",
        "success_grading": None}}
    for field in ("instruction_language", "task_pair_id", "source_language"):
        if field in task:
            session["meta"][field] = task[field]
    return session, gold, labels, dict(stats)


def annotate(instance: Path) -> dict:
    task = json.loads((instance / "task.json").read_text())
    registry = json.loads((instance / "private/registry.json").read_text())
    capture = instance / "capture/api_requests.jsonl.xz"
    items = C.session_items(C.read_requests(capture))
    run = json.loads((instance / "run.json").read_text())
    session_id = "creddata-pilot-" + run["session_id"]
    session, gold, labels, stats = label_items(task, registry, items, session_id)
    session["meta"]["run_status"] = run["status"]
    # Failed/truncated runs stay inspectable, but do not silently become training examples.
    if run["status"] != "finished":
        session["meta"]["allowed_use"] = []
    output = {"sessions.jsonl": (json.dumps(session, ensure_ascii=False) + "\n").encode(),
              "gold.jsonl": b"".join((json.dumps(r, ensure_ascii=False) + "\n").encode() for r in gold),
              "labels.jsonl": b"".join((json.dumps(r, ensure_ascii=False) + "\n").encode() for r in labels),
              "summary.json": T.jb({"items": len(items), "gold_spans": len(gold), **stats,
                                     "annotation_complete": False, "success_grading": None})}
    T.write_tree(instance / "labeled", output)
    return json.loads(output["summary.json"])


def run_one(instance: Path, env: dict, model: str, budget: float, timeout: int,
            auth_mode: str = "api", haiku_only: bool = False, effort: str = "low") -> dict:
    task = json.loads((instance / "task.json").read_text())
    registry = json.loads((instance / "private/registry.json").read_text())
    source = instance / "workspace" / task["source_filename"]
    if T.sha(source.read_bytes()) != registry["source_sha256"]:
        raise ValueError("workspace changed since secret instantiation")
    if (instance / "run.json").exists() or (instance / "capture").exists():
        raise ValueError("this instance has already been run; instantiate a fresh run directory")
    (instance / "capture").mkdir()
    # The agent works in a neutral copy: the instance path names the dataset and sits next to private/.
    WORK_BASE.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="project-", dir=WORK_BASE))
    shutil.copytree(instance / "workspace", work, dirs_exist_ok=True)
    upstream = env.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
    proxy_type = HaikuOnlyProxy if haiku_only else CaptureProxy
    proxy = proxy_type(instance / "capture/api_requests.jsonl.xz", upstream)
    session_id = str(uuid.uuid4())
    argv = ["claude", "-p", (instance / "workspace/request.md").read_text(),
            "--model", model, "--effort", effort, "--output-format", "stream-json", "--verbose",
            "--no-session-persistence", "--session-id", session_id,
            "--safe-mode", "--setting-sources", "project", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}', "--tools", "Read,Write,Edit,Glob,Grep,Bash",
            "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash", "--permission-mode", "acceptEdits"]
    if auth_mode == "api":
        # --bare deliberately disables OAuth, so it must not be passed for account runs.
        argv.extend(["--bare", "--max-budget-usd", str(budget)])
    started = time.monotonic()
    status, exit_code, final = "started", None, {}
    try:
        runtime_env = {**env, "ANTHROPIC_BASE_URL": proxy.start(), "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        with (instance / "capture/stream.jsonl").open("w") as stdout, \
                (instance / "capture/stderr.txt").open("w") as stderr:
            proc = subprocess.Popen(argv, cwd=work, env=runtime_env, stdout=stdout, stderr=stderr,
                                    stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                status = "timeout"
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
        for line in (instance / "capture/stream.jsonl").read_text().splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "result":
                final = event
        if status != "timeout":
            status = "finished" if exit_code == 0 and final.get("subtype") == "success" and not final.get("is_error") \
                else "incomplete_or_error"
    finally:
        request_count = proxy.stop()
        shutil.copytree(work, instance / "workspace_after")
        shutil.rmtree(work)
        accepted = C.read_requests(instance / "capture/api_requests.jsonl.xz")
        models_sent = sorted({body["model"] for body in accepted if isinstance(body.get("model"), str)})
        if status == "finished" and not accepted:
            status = "capture_missing"
        summary = {"task_id": task["task_id"], "family": task["family"], "session_id": session_id,
                   "status": status, "exit_code": exit_code, "model_requested": model, "effort": effort,
                   "auth_mode": auth_mode, "haiku_only": haiku_only, "models_sent": models_sent,
                   "budget_usd": budget if auth_mode == "api" else None,
                   "cost_usd": final.get("total_cost_usd"),
                   "cost_meaning": "api_charge" if auth_mode == "api" else "api_equivalent_estimate_not_subscription_charge",
                   "num_turns": final.get("num_turns"), "result_subtype": final.get("subtype"),
                   "elapsed_s": round(time.monotonic() - started, 2), "captured_requests": request_count,
                   "success_grading": None}
        (instance / "run.json").write_bytes(T.jb(summary))
    summary["annotation"] = annotate(instance)
    return summary


def select_instances(root: Path, selection: str, instruction_language: str | None = None) -> list[Path]:
    """Select by task metadata, supporting both hand-authored and automatically generated IDs."""
    if selection in {"one-per-family", "all"}:
        available = sorted(p for p in root.iterdir() if (p / "task.json").is_file())
        if instruction_language:
            available = [p for p in available if json.loads((p / "task.json").read_text()).get("instruction_language", "ko") == instruction_language]
        if selection == "one-per-family":
            languages = [instruction_language] if instruction_language else sorted({
                json.loads((p / "task.json").read_text()).get("instruction_language", "ko") for p in available})
            families = {(family, language): [] for family in T.FAMILIES for language in languages}
            for path in available:
                task = json.loads((path / "task.json").read_text())
                key = task["family"], task.get("instruction_language", "ko")
                if key in families:
                    families[key].append(path)
            if any(not members for members in families.values()):
                raise ValueError("one-per-family requires an instance from each family and instruction language")
            paths = [families[family, language][0] for family in T.FAMILIES for language in languages]
        else:
            paths = available
    else:
        names = selection.split(",")
        if len(names) != len(set(names)):
            raise ValueError("duplicate task IDs")
        paths = [root / name for name in names]
    paths = [p.resolve() for p in paths]
    if not paths or any(p.parent != root.resolve() or not (p / "task.json").is_file() for p in paths):
        raise ValueError("unknown task instance")
    if instruction_language and any(json.loads((p / "task.json").read_text()).get("instruction_language", "ko") != instruction_language
                                    for p in paths):
        raise ValueError("explicit task does not match the requested instruction language")
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--instances", type=Path, required=True)
    run.add_argument("--tasks", default="one-per-family", help="one-per-family, all, or comma-separated task IDs")
    run.add_argument("--instruction-language", choices=("ko", "en"), help="select a natural-language variant")
    run.add_argument("--env-file", type=Path)
    run.add_argument("--auth", choices=("api", "subscription"), default="api")
    run.add_argument("--model", default="sonnet")
    run.add_argument("--haiku-only", action="store_true", help="block non-Haiku requests before sending upstream")
    run.add_argument("--effort", default="low", choices=("low", "medium", "high"))
    run.add_argument("--budget", type=float, default=1.0, help="Claude CLI budget per run, in USD")
    run.add_argument("--timeout", type=int, default=240)
    run.add_argument("--check-only", action="store_true", help="check API configuration and task paths without API calls")
    label = sub.add_parser("label")
    label.add_argument("instance", type=Path)
    args = parser.parse_args()
    if args.command == "label":
        print(json.dumps(annotate(args.instance), indent=2))
        return
    try:
        if args.auth == "subscription" and args.env_file:
            parser.error("subscription mode does not accept an API environment file")
        if args.haiku_only and "haiku" not in args.model.lower():
            parser.error("--haiku-only needs --model haiku or a full Haiku model ID")
        env = subscription_environment() if args.auth == "subscription" else api_environment(args.env_file)
    except ValueError as error:
        parser.exit(2, str(error) + "\n")
    if args.budget <= 0 or args.timeout <= 0:
        parser.error("budget and timeout must be positive")
    try:
        paths = select_instances(args.instances, args.tasks, args.instruction_language)
    except ValueError as error:
        parser.error(str(error))
    if args.check_only:
        print(json.dumps({"auth_mode": args.auth, "auth_configured": True, "tasks": [p.name for p in paths], "api_calls": 0}))
        return
    for path in paths:
        print(json.dumps(run_one(path, env, args.model, args.budget, args.timeout, args.auth, args.haiku_only, args.effort)), flush=True)


if __name__ == "__main__":
    main()
