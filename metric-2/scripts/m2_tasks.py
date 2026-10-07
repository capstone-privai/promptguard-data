"""Metric 2 tasks: load the task templates, build a workspace with deterministic synthetic secrets, and check
what an agent left behind.

A task is a folder under metric-2/tasks/<task_id>/:
  task.json   prompt, category, secrets, checks, oracle solution (see metric-2/README.md)
  workspace/  the project the agent works in; {{secret:NAME}} marks where a secret value goes
  check.py    optional, task-specific check functions named by {"kind": "python", "func": ...}

Secret values come from the same deterministic generator as the metric 1 datasets
(metric-1/scripts/dataset_build.py), seeded with the task id and the secret name, so every build of a task is
byte-identical. They are public synthetic values: never use them to authenticate anywhere.

Gold for metric 2 is every declared secret: these are the only values the gold condition masks. Each derived
form a task declares (base64, URL-encoded, JSON-escaped) is a gold value of its own, and the base value is gold
too, so a decoded form that shows up in a tool result is masked as well.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = REPO_ROOT / "metric-2" / "tasks"
sys.path.insert(0, str(REPO_ROOT / "metric-1" / "scripts"))
import dataset_build as m1  # noqa: E402  (shared synthetic value generator)

SEED_PREFIX = "metric2"
SECRET_REF = re.compile(r"\{\{secret:([a-z][a-z0-9_]*)\}\}")
# A placeholder a masking layer may have written back into a file: [PASSWORD_1], [TOKEN_3], [API_KEY_2] ...
PLACEHOLDER = re.compile(r"\[[A-Z][A-Z0-9_]*_\d+\]")
ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CLASSES = {"l": "abcdefghijkmnopqrstuvwxyz", "u": "ABCDEFGHJKLMNPQRSTUVWXYZ", "d": "23456789",
           "s": "!#%*+-=?@^_~", "a": ALNUM, "h": "0123456789abcdef"}
TEXT_SUFFIXES = {"", ".env", ".txt", ".md", ".json", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".toml",
                 ".py", ".js", ".sh", ".log", ".sql", ".csv", ".production", ".staging", ".dev", ".prod"}


# ---- secrets -----------------------------------------------------------------------------------------------

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def jwt_with_claims(seed: str, claims: dict) -> str:
    header = b64url(b'{"alg":"HS256","typ":"JWT"}')
    payload = b64url(json.dumps(claims, separators=(",", ":")).encode())
    signature = b64url(hmac.new(m1.value(seed + ":jwt-key", 32).encode(), f"{header}.{payload}".encode(),
                                hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def from_pattern(seed: str, pattern: str) -> str:
    """One character per pattern letter: l lower, u upper, d digit, s symbol, a alphanumeric, h hex."""
    return "".join(m1.value(f"{seed}:{i}", 1, CLASSES[c]) for i, c in enumerate(pattern))


# kind -> (gold type, generator(seed, spec) -> value)
KINDS = {
    "password16": ("PASSWORD", lambda s, _: m1.value(s, 16, ALNUM)),
    "password_dollar": ("PASSWORD", lambda s, _: m1.value(s + ":a", 6, ALNUM) + "$"
                        + m1.value(s + ":b", 1, CLASSES["l"]) + m1.value(s + ":c", 8, ALNUM)),
    "pattern": ("PASSWORD", lambda s, spec: from_pattern(s, spec["pattern"])),
    "stripe_live": ("SECRET", lambda s, _: "sk_live_" + m1.value(s, 24, ALNUM)),
    "stripe_test": ("SECRET", lambda s, _: "sk_test_" + m1.value(s, 24, ALNUM)),
    "jwt_claims": ("TOKEN", lambda s, spec: jwt_with_claims(s, spec["claims"])),
    "literal": (None, lambda _s, spec: spec["value"]),
    **{kind: (kind_type, lambda s, _spec, g=generate: g(s)) for kind, (kind_type, generate) in m1.GENERATORS.items()},
}


@dataclass
class Secret:
    name: str
    type: str
    value: str


def make_secrets(task_id: str, specs: dict) -> dict[str, Secret]:
    out: dict[str, Secret] = {}
    for name, spec in specs.items():  # a derived secret names a base declared before it
        if "from" in spec:
            base = out[spec["from"]]
            value, kind_type = base.value, base.type
            for t in spec.get("transforms", []):
                t_name, _, t_arg = t.partition("=")
                value, new_type = m1.transform(value, t_name, t_arg or None)
                kind_type = new_type or kind_type
        else:
            kind_type, generate = KINDS[spec["kind"]]
            value = generate(f"{SEED_PREFIX}:{task_id}:{name}", spec)
        out[name] = Secret(name, spec.get("type") or kind_type, value)
    return out


def gold_rows(secrets: dict[str, Secret]) -> list[dict]:
    """Every surface form the gold condition masks. A PEM key also contributes its body lines, so a partial
    print of the key (head, sed -n) is masked too."""
    rows, seen = [], set()
    for s in secrets.values():
        forms = [s.value]
        if "PRIVATE KEY-----" in s.value:
            forms += [line for line in s.value.replace("\\n", "\n").split("\n") if line and "-----" not in line]
            forms.append(s.value.replace("\\n", "\n"))
        for form in forms:
            if form not in seen:
                seen.add(form)
                rows.append({"name": s.name, "type": s.type, "value": form})
    return rows


# ---- tasks -------------------------------------------------------------------------------------------------

@dataclass
class Task:
    id: str
    dir: Path
    spec: dict
    secrets: dict[str, Secret] = field(default_factory=dict)

    @property
    def prompt(self) -> str:
        return self.spec["prompt"]

    @property
    def category(self) -> str:
        return self.spec["category"]

    def fill(self, text: str) -> str:
        return SECRET_REF.sub(lambda m: self.secrets[m.group(1)].value, text)


def load_task(path: Path) -> Task:
    spec = json.loads((path / "task.json").read_text(encoding="utf-8"))
    if spec["id"] != path.name:
        raise ValueError(f"{path}: task.json id {spec['id']!r} != folder name")
    task = Task(spec["id"], path, spec)
    task.secrets = make_secrets(task.id, spec.get("secrets", {}))
    return task


def load_tasks(ids: list[str] | None = None) -> list[Task]:
    tasks = [load_task(p) for p in sorted(TASKS_DIR.iterdir()) if (p / "task.json").is_file()]
    if ids and ids != ["all"]:
        wanted = set(ids)
        tasks = [t for t in tasks if t.id in wanted or t.id.split("-")[0] in wanted]
        missing = wanted - {t.id for t in tasks} - {t.id.split("-")[0] for t in tasks}
        if missing:
            raise SystemExit(f"unknown task(s): {sorted(missing)}")
    return tasks


def is_text(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name.startswith(".env")


def git(ws: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ws), "-c", "user.name=metric2", "-c", "user.email=metric2@example.invalid",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=check)


def build(task: Task, dest: Path) -> dict[str, str]:
    """Write the task workspace to dest (a fresh git repository with one commit). Returns {path: text} of the
    built text files, which the integrity check compares against."""
    if dest.exists():
        shutil.rmtree(dest)
    src = task.dir / "workspace"
    built: dict[str, str] = {}
    for path in sorted(src.rglob("*")):
        if path.is_dir() or path.name == ".DS_Store":
            continue
        rel = path.relative_to(src).as_posix()
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if is_text(path):
            text = task.fill(path.read_text(encoding="utf-8"))
            if SECRET_REF.search(text) or "{{secret:" in text:
                raise ValueError(f"{task.id}/{rel}: unresolved secret reference")
            target.write_text(text, encoding="utf-8")
            built[rel] = text
        else:
            shutil.copyfile(path, target)
        shutil.copymode(path, target)
    for gen in task.spec.get("generated", []):  # content derived from other files or from the secrets
        GENERATED[gen["kind"]](dest, gen, built, task)
    git(dest, "init", "-q", "-b", "main")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "initial import")
    for argv in task.spec.get("setup", []):
        subprocess.run([task.fill(a) for a in argv], cwd=dest, check=True, capture_output=True)
    return built


def gen_sha256_manifest(dest: Path, gen: dict, built: dict[str, str], task: "Task"):
    """Writes a manifest of sha256 sums; entries listed in gen["wrong"] get a sum that does not match."""
    artifacts = []
    for name in gen["files"]:
        digest = hashlib.sha256((dest / gen["dir"] / name).read_bytes()).hexdigest()
        if name in gen.get("wrong", []):
            digest = hashlib.sha256(digest.encode()).hexdigest()
        artifacts.append({"file": name, "sha256": digest})
    text = json.dumps({"release": gen["release"], "artifacts": artifacts}, indent=2) + "\n"
    (dest / gen["path"]).write_text(text, encoding="utf-8")
    built[gen["path"]] = text


def keystream_xor(key: bytes, data: bytes) -> bytes:
    stream = b"".join(hashlib.sha256(key + i.to_bytes(4, "big")).digest() for i in range(len(data) // 32 + 1))
    return bytes(a ^ b for a, b in zip(data, stream))


def gen_keyed_payload(dest: Path, gen: dict, built: dict[str, str], task: "Task"):
    """Fills a CLI script's __SECRET_SHA256__ and __PAYLOAD__ markers: the task's data (gen["data"], a JSON file
    in the task folder) encrypted with the secret, so the only way to the data is to pass the secret to the CLI."""
    secret = task.secrets[gen["secret"]].value
    data = json.dumps(json.loads((task.dir / gen["data"]).read_text(encoding="utf-8")), separators=(",", ":"))
    key = hashlib.sha256(("m2-payload:" + secret).encode()).digest()
    payload = base64.b64encode(keystream_xor(key, data.encode())).decode()
    text = built[gen["path"]].replace("__SECRET_SHA256__", hashlib.sha256(secret.encode()).hexdigest())
    text = text.replace("__PAYLOAD__", payload)
    (dest / gen["path"]).write_text(text, encoding="utf-8")
    built[gen["path"]] = text


GENERATED = {"sha256_manifest": gen_sha256_manifest, "keyed_payload": gen_keyed_payload}


# ---- checks ------------------------------------------------------------------------------------------------

def norm(value) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().strip("`'\"").lower()


def norm_path(value) -> str:
    return norm(value).removeprefix("./")


def to_bool(value):
    if isinstance(value, bool):
        return value
    text = norm(value)
    return {"true": True, "yes": True, "false": False, "no": False}.get(text)


def to_time(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def match_answer(got, check: dict) -> bool:
    how, expect = check.get("match", "text"), check.get("expect")
    if got is None:
        return False
    if how == "text":
        options = check.get("one_of", [expect])
        return norm(got) in {norm(o) for o in options}
    if how == "contains":
        return norm(expect) in norm(got)
    if how == "number":  # also reads "10.00", "Decimal('10.00')", "90 minutes"
        if isinstance(got, bool):
            return False
        found = re.search(r"-?\d+(?:\.\d+)?", str(got))
        return found is not None and abs(float(found.group()) - float(expect)) < 1e-9
    if how == "bool":
        return to_bool(got) is expect
    if how == "set":
        if not isinstance(got, list):
            return False
        return {norm_path(g) for g in got} == {norm_path(e) for e in expect}
    if how == "time":
        a, b = to_time(got), to_time(expect)
        return a is not None and a == b
    raise ValueError(f"unknown answer match {how!r}")


def read_answer(ws: Path, path: str) -> tuple[dict | None, str]:
    file = ws / path
    if not file.is_file():
        return None, f"{path} missing"
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, f"{path} is not JSON ({e})"
    return (data, "") if isinstance(data, dict) else (None, f"{path} is not an object")


def run_check(task: Task, ws: Path, check: dict, built: dict[str, str],
              remotes: dict[str, str] | None = None) -> tuple[bool, str]:
    kind = check["kind"]
    if kind == "answer":
        data, err = read_answer(ws, check.get("file", "answer.json"))
        if data is None:
            return False, err
        got = data.get(check["key"])
        return match_answer(got, check), f"{check['key']}={got!r}"
    if kind == "file_regex":
        file = ws / check["path"]
        text = file.read_text(encoding="utf-8") if file.is_file() else ""
        found = re.search(task.fill(check["pattern"]), text, re.M) is not None
        ok = found != check.get("negate", False)
        return ok, ("matched" if found else "no match") + f" /{check['pattern']}/ in {check['path']}"
    if kind == "secret_in_file":
        file = ws / check["path"]
        text = file.read_text(encoding="utf-8") if file.is_file() else ""
        n = text.count(task.secrets[check["secret"]].value)
        return n >= check.get("min", 1), f"{check['secret']} x{n} in {check['path']}"
    if kind == "unchanged":
        file = ws / check["path"]
        same = file.is_file() and file.read_text(encoding="utf-8") == built[check["path"]]
        return same, f"{check['path']} {'unchanged' if same else 'changed'}"
    if kind == "command":
        try:
            proc = subprocess.run([task.fill(a) for a in check["run"]], cwd=ws, capture_output=True, text=True,
                                  timeout=check.get("timeout", 60))
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, f"{' '.join(check['run'])}: {type(e).__name__}"
        ok = proc.returncode == check.get("exit", 0)
        if ok and "stdout" in check:
            ok = re.search(check["stdout"], proc.stdout) is not None
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
        return ok, f"exit {proc.returncode}: {tail[0][:120]}"
    if kind == "git_remote":  # remotes: saved `git remote` URLs, when the repository itself is gone
        if remotes is None:
            remotes = git_remotes(ws)
        ok = remotes.get(check.get("remote", "origin")) == task.fill(check["expect"])
        return ok, "remote matches" if ok else "remote differs"
    if kind == "python":
        module = load_check_module(task)
        return getattr(module, check["func"])(ws, {n: s.value for n, s in task.secrets.items()})
    raise ValueError(f"{task.id}: unknown check kind {kind!r}")


def load_check_module(task: Task):
    spec = importlib.util.spec_from_file_location(f"m2check_{task.id.replace('-', '_')}", task.dir / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def integrity(task: Task, ws: Path, built: dict[str, str]) -> tuple[bool, str]:
    """Secrets the agent did not need to touch are still in their files, and no masking placeholder was written
    into the workspace. allow_removed lists (secret, path) pairs the task asks the agent to move away."""
    allowed = {tuple(p) for p in task.spec.get("integrity", {}).get("allow_removed", [])}
    problems = []
    for rel, original in built.items():
        file = ws / rel
        text = file.read_text(encoding="utf-8", errors="replace") if file.is_file() else None
        for name, s in task.secrets.items():
            if s.value in original and (name, rel) not in allowed and (text is None or s.value not in text):
                problems.append(f"{name} lost from {rel}")
    for file in sorted(p for p in ws.rglob("*") if p.is_file() and ".git" not in p.relative_to(ws).parts):
        rel = file.relative_to(ws).as_posix()
        if not is_text(file):
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        before = set(PLACEHOLDER.findall(built.get(rel, "")))
        written = sorted(set(PLACEHOLDER.findall(text)) - before)
        if written:
            problems.append(f"placeholder {', '.join(written[:3])} written to {rel}")
    return not problems, "; ".join(problems) or "secrets intact"


def git_remotes(ws: Path) -> dict[str, str]:
    proc = git(ws, "remote", check=False)
    names = proc.stdout.split() if proc.returncode == 0 else []
    return {n: git(ws, "remote", "get-url", n, check=False).stdout.strip() for n in names}


def check_task(task: Task, ws: Path, built: dict[str, str], remotes: dict[str, str] | None = None) -> dict:
    results = []
    for i, check in enumerate(task.spec["checks"]):
        try:
            ok, detail = run_check(task, ws, check, built, remotes)
        except Exception as e:  # a broken workspace must not stop the batch
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append({"check": check.get("name") or f"{check['kind']}#{i}", "ok": bool(ok), "detail": detail})
    ok_integrity, detail = integrity(task, ws, built)
    task_ok = all(r["ok"] for r in results)
    return {"success": task_ok and ok_integrity, "task_ok": task_ok, "integrity_ok": ok_integrity,
            "integrity": detail, "checks": results}


# ---- oracle solution (self-test) ---------------------------------------------------------------------------

def apply_solution(task: Task, ws: Path):
    for step in task.spec["solution"]:
        if "answer" in step:
            (ws / "answer.json").write_text(json.dumps(step["answer"], ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
        elif "replace" in step:
            file = ws / step["replace"]
            text = file.read_text(encoding="utf-8")
            old, new = task.fill(step["old"]), task.fill(step["new"])
            if old not in text:
                raise ValueError(f"{task.id}: solution text not found in {step['replace']}: {step['old'][:60]!r}")
            file.write_text(text.replace(old, new, step.get("count", -1)), encoding="utf-8")
        elif "append" in step:
            with (ws / step["append"]).open("a", encoding="utf-8") as f:
                f.write(task.fill(step["text"]))
        elif "run" in step:
            subprocess.run([task.fill(a) for a in step["run"]], cwd=ws, check=True, capture_output=True)
        else:
            raise ValueError(f"{task.id}: unknown solution step {step}")


def corrupt_with_placeholder(task: Task, ws: Path, built: dict[str, str]) -> bool:
    """Replace the first secret found in a workspace file with [PASSWORD_1], the way an agent that only saw the
    masked text would write it back. Returns False if no file holds a secret."""
    for rel in built:
        file = ws / rel
        if not file.is_file():
            continue
        text = file.read_text(encoding="utf-8")
        for s in task.secrets.values():
            if s.value in text:
                file.write_text(text.replace(s.value, "[PASSWORD_1]"), encoding="utf-8")
                return True
    return False
