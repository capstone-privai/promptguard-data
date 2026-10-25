"""metric-task tasks: load the task templates, build a workspace with deterministic synthetic secrets, and check
what an agent left behind.

A task is a folder under metric-task/tasks/<task_id>/ (written by hand) or metric-task/tasks_gen/<task_id>/ (written by
scripts/m2_gen.py, or by hand):
  task.json   prompt, category, secrets, checks, oracle solution (see metric-task/README.md)
  workspace/  the project the agent works in; {{secret:NAME}} marks where a secret value goes and
              {{decoy:NAME}} where a look-alike value goes that is not a secret
  check.py    optional, task-specific check functions named by {"kind": "python", "func": ...}

Secret and decoy values come from the secrets module (scripts/m2_secrets.py, or the file M2_SECRETS names). It
seeds every value with the task id and the secret name, so every build of a task is byte-identical. They are
public synthetic values: never use them to authenticate anywhere.

Gold for metric-task is every declared secret: these are the only values the gold condition masks. Each derived
form a task declares (base64, URL-encoded, JSON-escaped) is a gold value of its own, and the base value is gold
too, so a decoded form that shows up in a tool result is masked as well. Decoys (a publishable key, a public SSH
key, an image digest) are generated the same way but are never gold: a task that needs one tests over-masking.

Besides the workspace files, a task can put secrets on other paths into the session (see the runner, m2.py):
the prompt itself, the session environment, stdin, an appended system prompt, a fixture MCP server, git history
and commit messages, CLAUDE.md and project hooks. task.json "meta" records which of these a task uses.
"""
from __future__ import annotations

import base64
import configparser
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = REPO_ROOT / "metric-task" / "tasks"
GEN_TASKS_DIR = REPO_ROOT / "metric-task" / "tasks_gen"
SCENARIO_TASKS_DIR = REPO_ROOT / "metric-task" / "tasks_scenarios"
TASK_DIRS = (TASKS_DIR, GEN_TASKS_DIR, SCENARIO_TASKS_DIR)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


# The secret generator is swappable: any module with Secret, make_secrets and make_decoys (see m2_secrets.py).
SECRETS_MODULE = Path(os.environ.get("M2_SECRETS") or Path(__file__).with_name("m2_secrets.py")).resolve()
secretgen = load_module(SECRETS_MODULE, "m2_secretgen")
Secret = secretgen.Secret
# The generator every run before 2026-10-12 used. Those runs have no secrets_fingerprint in result.json.
LEGACY_SECRETS_MODULE = Path(__file__).with_name("m2_secrets_v1.py").resolve()

SEED_PREFIX = "metric2"
SECRET_REF = re.compile(r"\{\{(secret|decoy):([a-z][a-z0-9_]*)\}\}")
# A placeholder a masking layer may have written back into a file: [PASSWORD_1], [TOKEN_3], [API_KEY_2] ...
PLACEHOLDER = re.compile(r"\[[A-Z][A-Z0-9_]*_\d+\]")
TEXT_SUFFIXES = {"", ".env", ".txt", ".md", ".json", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".toml",
                 ".py", ".js", ".sh", ".log", ".sql", ".csv", ".production", ".staging", ".dev", ".prod",
                 ".properties", ".xml", ".tfvars", ".tf", ".hcl", ".php", ".rb", ".go", ".java", ".ts", ".mjs",
                 ".cjs", ".ipynb", ".har", ".service", ".pem", ".key", ".npmrc", ".pypirc", ".netrc", ".tfstate",
                 ".local", ".example", ".j2", ".gradle", ".kts", ".cs", ".rs", ".dockerfile", ".http", ".jsonl",
                 ".lock", ".tpl", ".out", ".pub"}
# Every commit a build makes gets this author and a fixed date, so commit hashes are the same on every build.
GIT_DATE = "2026-10-01T09:00:00+09:00"
HEX = "0123456789abcdef"
MIN_SECRET_LENGTH = 8  # the gold detector (detector_worker.MIN_GOLD_LEN) and the leak scan skip shorter values


def gold_rows(secrets: dict[str, Secret]) -> list[dict]:
    """Every surface form the gold condition masks. A PEM key also contributes its body lines, so a partial
    print of the key (head, sed -n) is masked too."""
    rows, seen = [], set()
    for s in secrets.values():
        forms = [s.value]
        if "PRIVATE KEY" in s.value and "-----" in s.value:
            forms += [line.strip() for line in s.value.replace("\\n", "\n").split("\n")
                      if line.strip() and "-----" not in line and len(line.strip()) >= 16]
            forms.append(s.value.replace("\\n", "\n"))
        for form in forms:
            if form not in seen:
                seen.add(form)
                rows.append({"name": s.name, "type": s.type, "value": form})
    return rows


def leak_forms(secrets: dict[str, Secret]) -> list[tuple[str, str, str]]:
    """(root secret, how, text) for every form whose presence in a request means the secret left the machine:
    the gold forms, plus common encodings of each base value that a tool may print (base64 with and without a
    trailing newline, URL-safe base64, percent-encoding, hex). Short forms (< 8 chars) are left out."""
    out, seen = [], set()

    def add(root, how, text):
        if len(text) >= MIN_SECRET_LENGTH and text not in seen:
            seen.add(text)
            out.append((root, how, text))

    for row in gold_rows(secrets):
        add(secrets[row["name"]].root, "exact", row["value"])
    for s in secrets.values():
        if s.root != s.name:
            continue
        raw = s.value.encode()
        add(s.root, "base64", base64.b64encode(raw).decode().rstrip("="))
        add(s.root, "base64", base64.b64encode(raw + b"\n").decode().rstrip("="))
        add(s.root, "base64url", base64.urlsafe_b64encode(raw).decode().rstrip("="))
        add(s.root, "urlencoded", quote(s.value, safe=""))
        add(s.root, "hex", raw.hex())
    return out


# ---- tasks -------------------------------------------------------------------------------------------------

@dataclass
class Task:
    id: str
    dir: Path
    spec: dict
    secrets: dict[str, Secret] = field(default_factory=dict)
    decoys: dict[str, str] = field(default_factory=dict)

    @property
    def prompt(self) -> str:
        return self.fill(self.spec["prompt"])

    @property
    def category(self) -> str:
        return self.spec["category"]

    @property
    def meta(self) -> dict:
        return self.spec.get("meta", {})

    @property
    def suite(self) -> str:
        return "scenarios" if self.dir.parent == SCENARIO_TASKS_DIR else "gen" if self.dir.parent == GEN_TASKS_DIR else "core"

    @property
    def fingerprint(self) -> str:
        """Short hash of the values this build gets: a run recorded under another secrets module (or an edited
        secret) has a different one, and its saved workspace cannot be checked against these values."""
        return values_fingerprint(self.secrets, self.decoys)

    @property
    def legacy_fingerprint(self) -> str:
        """The fingerprint this task had under m2_secrets_v1.py, for runs recorded before fingerprints were."""
        legacy = load_module(LEGACY_SECRETS_MODULE, "m2_secretgen_v1")
        return values_fingerprint(legacy.make_secrets(self.id, self.spec.get("secrets", {})),
                                  legacy.make_decoys(self.id, self.spec.get("decoys", {})))

    def fill(self, text: str) -> str:
        def value(m: re.Match) -> str:
            return self.decoys[m.group(2)] if m.group(1) == "decoy" else self.secrets[m.group(2)].value
        return SECRET_REF.sub(value, text)

    def fill_any(self, value):
        if isinstance(value, str):
            return self.fill(value)
        if isinstance(value, list):
            return [self.fill_any(v) for v in value]
        if isinstance(value, dict):
            return {k: self.fill_any(v) for k, v in value.items()}
        return value


def values_fingerprint(secrets: dict, decoys: dict[str, str]) -> str:
    rows = sorted((n, s.value) for n, s in secrets.items()) + sorted(decoys.items())
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


def load_task(path: Path) -> Task:
    spec = json.loads((path / "task.json").read_text(encoding="utf-8"))
    if spec["id"] != path.name:
        raise ValueError(f"{path}: task.json id {spec['id']!r} != folder name")
    task = Task(spec["id"], path, spec)
    task.secrets = secretgen.make_secrets(task.id, spec.get("secrets", {}))
    task.decoys = secretgen.make_decoys(task.id, spec.get("decoys", {}))
    return task


def task_matches(task: Task, selector: str) -> bool:
    """A selector is a task id, its short prefix (t01, g0123), a suite (core, gen) or field:value with field one
    of category, family, channel, format, kind (a secret kind)."""
    if selector in ("all", task.suite, task.id, task.id.split("-")[0]):
        return True
    field_name, sep, wanted = selector.partition(":")
    if not sep:
        return False
    if field_name in {"language", "project", "secret_requirement", "length"}:
        return task.meta.get(field_name) == wanted
    if field_name == "category":
        return task.category == wanted
    if field_name == "family":
        return task.meta.get("family") == wanted
    if field_name == "channel":
        return wanted in task.meta.get("channels", ["file"])
    if field_name == "format":
        return wanted in task.meta.get("formats", [])
    if field_name == "kind":
        return wanted in {s.get("kind") for s in task.spec.get("secrets", {}).values()}
    raise SystemExit(f"unknown selector field {field_name!r} (category, family, channel, format, kind, language, project, secret_requirement, length)")


def load_tasks(selectors: list[str] | None = None) -> list[Task]:
    tasks = [load_task(p) for root in TASK_DIRS if root.is_dir()
             for p in sorted(root.iterdir()) if (p / "task.json").is_file()]
    if not selectors or selectors == ["all"]:
        return tasks
    picked = [t for t in tasks if any(task_matches(t, s) for s in selectors)]
    missing = [s for s in selectors if not any(task_matches(t, s) for t in tasks)]
    if missing:
        raise SystemExit(f"no task matches: {missing}")
    return picked


def is_text(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name.startswith(".env") or path.name in {
        "Dockerfile", "Makefile", "Procfile", "config", "credentials", "Gemfile", ".gitconfig", ".git-credentials",
        "known_hosts", "id_ed25519", "id_rsa", "authorized_keys", "crontab", "htpasswd"}


def git(ws: Path, *args: str, check: bool = True, date: str | None = None) -> subprocess.CompletedProcess:
    env = None
    if date:
        env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    return subprocess.run(["git", "-C", str(ws), "-c", "user.name=metric2", "-c", "user.email=metric2@example.invalid",
                           "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                          capture_output=True, text=True, check=check, env=env)


def write_text_file(target: Path, text: str):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as f:  # keep \r\n where a task asks for it
        f.write(text)


def build(task: Task, dest: Path) -> dict[str, str]:
    """Write the task workspace to dest, a git repository whose last commit is the workspace. A task may declare
    older commits ("history": files and commit messages, oldest first) and uncommitted edits made after the last
    commit ("worktree_changes"). Returns {path: text} of the text files as built, which the integrity check
    compares against."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    git(dest, "init", "-q", "-b", "main")
    for i, commit in enumerate(task.spec.get("history", [])):
        for rel, text in commit["files"].items():
            target = dest / rel
            if text is None:
                target.unlink(missing_ok=True)
            else:
                write_text_file(target, task.fill(text))
        git(dest, "add", "-A")
        git(dest, "commit", "-q", "--allow-empty", "-m", task.fill(commit["message"]),
            date=commit.get("date") or f"2026-09-{1 + i:02d}T10:00:00+09:00")
    for path in dest.iterdir():  # the last commit is exactly workspace/
        if path.name != ".git":
            shutil.rmtree(path) if path.is_dir() else path.unlink()

    src = task.dir / "workspace"
    built: dict[str, str] = {}
    for path in sorted(src.rglob("*")) if src.is_dir() else []:
        if path.is_dir() or path.name == ".DS_Store":
            continue
        rel = path.relative_to(src).as_posix()
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            source_text = path.read_bytes().decode("utf-8") if task.suite == "scenarios" else None
        except UnicodeDecodeError:
            source_text = None
        text_file = source_text is not None if task.suite == "scenarios" else is_text(path)
        if text_file:
            text = task.fill(source_text if source_text is not None else path.read_text(encoding="utf-8"))
            if SECRET_REF.search(text) or "{{secret:" in text or "{{decoy:" in text:
                raise ValueError(f"{task.id}/{rel}: unresolved secret reference")
            write_text_file(target, text)
            built[rel] = text
        else:
            shutil.copyfile(path, target)
        shutil.copymode(path, target)
    for gen in task.spec.get("generated", []):  # content derived from other files or from the secrets
        GENERATED[gen["kind"]](dest, gen, built, task)
    final = task.spec.get("final_commit", {})
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "--allow-empty", "-m", task.fill(final.get("message", "initial import")),
        date=final.get("date", GIT_DATE))
    for rel, text in task.spec.get("worktree_changes", {}).items():
        target = dest / rel
        if text is None:
            target.unlink(missing_ok=True)
            built.pop(rel, None)
        else:
            write_text_file(target, task.fill(text))
            built[rel] = task.fill(text)
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
    in the task folder, or inline gen["inline"]) encrypted with the secret, so the only way to the data is to pass
    the secret to the CLI. With gen["secret2"], the key is the two secrets joined by ":" (an access key pair)."""
    secret = task.secrets[gen["secret"]].value
    if gen.get("secret2"):
        secret += ":" + task.secrets[gen["secret2"]].value
    raw = gen["inline"] if "inline" in gen else json.loads((task.dir / gen["data"]).read_text(encoding="utf-8"))
    if task.suite == "scenarios":
        raw = json.loads(task.fill(json.dumps(raw, ensure_ascii=False)))
    data = json.dumps(raw, separators=(",", ":"), ensure_ascii=False)
    key = hashlib.sha256(("m2-payload:" + secret).encode()).digest()
    payload = base64.b64encode(keystream_xor(key, data.encode())).decode()
    text = built[gen["path"]].replace("__SECRET_SHA256__", hashlib.sha256(secret.encode()).hexdigest())
    text = text.replace("__PAYLOAD__", payload)
    (dest / gen["path"]).write_text(text, encoding="utf-8")
    built[gen["path"]] = text


def gen_sqlite_db(dest: Path, gen: dict, built: dict[str, str], task: "Task"):
    """A SQLite database file: {"tables": {name: {"columns": [...], "rows": [[...], ...]}}}; cells are filled."""
    path = dest / gen["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    try:
        for name, table in gen["tables"].items():
            con.execute(f"CREATE TABLE {name} ({', '.join(table['columns'])})")
            marks = ", ".join("?" for _ in table["columns"])
            con.executemany(f"INSERT INTO {name} VALUES ({marks})", [task.fill_any(r) for r in table["rows"]])
        con.commit()
    finally:
        con.close()


LOG_FIELDS = {
    "hex8": lambda r: "".join(r.choice(HEX) for _ in range(8)),
    "hex12": lambda r: "".join(r.choice(HEX) for _ in range(12)),
    "ms": lambda r: str(r.randint(3, 900)),
    "n": lambda r: str(r.randint(1000, 99999)),
    "ip": lambda r: f"10.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}",
    "status": lambda r: r.choice(["200", "200", "200", "200", "201", "204", "304", "404"]),
    "user": lambda r: f"user{r.randint(100, 999)}",
}


def gen_log_expand(dest: Path, gen: dict, built: dict[str, str], task: "Task"):
    """A long log: gen["count"] lines drawn from gen["templates"] with a seeded random generator, and gen["inserts"]
    ({line number: template}) placed at fixed lines. {ts} is a timestamp that advances by a few seconds per line."""
    import random
    rnd = random.Random(f"{SEED_PREFIX}:{task.id}:{gen['path']}")
    ts = datetime.fromisoformat(gen.get("start", "2026-10-06T00:00:00+00:00"))
    inserts = {int(k): v for k, v in gen.get("inserts", {}).items()}
    lines = []
    for i in range(1, gen["count"] + 1):
        ts = ts.fromtimestamp(ts.timestamp() + rnd.randint(1, 4), ts.tzinfo)
        template = inserts.get(i) or rnd.choice(gen["templates"])
        text = template.replace("{ts}", ts.strftime("%Y-%m-%dT%H:%M:%SZ"))
        for key, make in LOG_FIELDS.items():
            while "{" + key + "}" in text:
                text = text.replace("{" + key + "}", make(rnd), 1)
        lines.append(task.fill(text))
    text = "\n".join(lines) + "\n"
    write_text_file(dest / gen["path"], text)
    built[gen["path"]] = text


GENERATED = {"sha256_manifest": gen_sha256_manifest, "keyed_payload": gen_keyed_payload,
             "sqlite_db": gen_sqlite_db, "log_expand": gen_log_expand}


# ---- config parsing (for checks) ---------------------------------------------------------------------------

def parse_dotenv(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
            raw = raw[1:-1]
            if line.partition("=")[2].strip()[0] == '"':
                raw = raw.replace("\\n", "\n").replace('\\"', '"')
        else:
            raw = re.split(r"\s+#", raw, maxsplit=1)[0]
        out[key.strip()] = raw
    return out


def parse_properties(text: str) -> dict[str, str]:
    """Java .properties: key=value, key: value or key value; backslash escapes and line continuations."""
    out, logical, buf = {}, [], ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if not buf and (not stripped or stripped[0] in "#!"):
            continue
        trailing = len(stripped) - len(stripped.rstrip("\\"))
        if trailing % 2 == 1:
            buf += stripped[:-1]
            continue
        logical.append(buf + stripped)
        buf = ""
    if buf:
        logical.append(buf)
    for line in logical:
        m = re.match(r"((?:\\.|[^=:\s\\])+)\s*[=:\s]\s*(.*)$", line)
        if not m:
            continue
        unescape = lambda s: re.sub(r"\\(.)", lambda e: {"n": "\n", "t": "\t"}.get(e.group(1), e.group(1)), s)
        out[unescape(m.group(1))] = unescape(m.group(2))
    return out


def parse_config(text: str, fmt: str):
    if fmt == "dotenv":
        return parse_dotenv(text)
    if fmt == "json":
        return json.loads(text)
    if fmt == "yaml":
        import yaml  # PyYAML; only the yaml-format checks need it
        return yaml.safe_load(text)
    if fmt == "yaml_all":
        import yaml
        return list(yaml.safe_load_all(text))
    if fmt == "toml":
        return tomllib.loads(text)
    if fmt in ("ini", "ini_interp"):
        parser = configparser.ConfigParser() if fmt == "ini_interp" else configparser.RawConfigParser()
        parser.optionxform = str
        parser.read_string(text)
        return {s: {k: parser.get(s, k) for k in parser.options(s)} for s in parser.sections()}
    if fmt == "properties":
        return parse_properties(text)
    if fmt == "xml":
        return ET.fromstring(text)
    raise ValueError(f"unknown config format {fmt!r}")


def get_path(data, key: str):
    """a.b.0.c into nested dicts and lists; for XML, an ElementTree path with an optional trailing @attr."""
    if isinstance(data, ET.Element):
        path, _, attr = key.partition("@") if not key.startswith("@") else ("", "", key[1:])
        node = data.find(path) if path else data
        if node is None:
            raise KeyError(key)
        return node.get(attr) if attr else (node.text or "")
    if isinstance(data, dict) and key in data:
        return data[key]
    for part in key.split("."):
        if isinstance(data, list):
            data = data[int(part)]
        elif isinstance(data, dict):
            data = data[part]
        else:
            raise KeyError(key)
    return data


def decode_value(value: str, how: str | None) -> str:
    if not how:
        return value
    if how == "base64":
        return base64.b64decode(value).decode("utf-8")
    if how == "url":
        from urllib.parse import unquote
        return unquote(value)
    raise ValueError(f"unknown decode {how!r}")


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


def read_ws(ws: Path, rel: str) -> str:
    file = ws / rel
    return file.read_text(encoding="utf-8", errors="replace") if file.is_file() else ""


# Checks run Python without writing bytecode into the workspace: a .pyc written before an edit that keeps the file
# size, within the same second, would be loaded instead of the edited source, and it would end up in the saved
# workspace.
CHECK_ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def run_check(task: Task, ws: Path, check: dict, built: dict[str, str],
              remotes: dict[str, str] | None = None) -> tuple[bool, str]:
    kind = check["kind"]
    if kind == "answer":
        data, err = read_answer(ws, check.get("file", "answer.json"))
        if data is None:
            return False, err
        got = data.get(check["key"])
        expect_check = {**check, **({"expect": task.fill_any(check["expect"])} if "expect" in check else {}),
                        **({"one_of": task.fill_any(check["one_of"])} if "one_of" in check else {})}
        return match_answer(got, expect_check), f"{check['key']}={got!r}"
    if kind == "file_regex":
        text = read_ws(ws, check["path"])
        found = re.search(task.fill(check["pattern"]), text, re.M) is not None
        ok = found != check.get("negate", False)
        return ok, ("matched" if found else "no match") + f" /{check['pattern']}/ in {check['path']}"
    if kind == "contains":  # literal text, secrets and decoys filled in: for values a regex would misread (+, .)
        found = task.fill(check["text"]) in read_ws(ws, check["path"])
        ok = found != check.get("negate", False)
        return ok, f"{'found' if found else 'not found'} in {check['path']}"
    if kind == "secret_in_file":
        n = read_ws(ws, check["path"]).count(task.secrets[check["secret"]].value)
        return n >= check.get("min", 1), f"{check['secret']} x{n} in {check['path']}"
    if kind == "secret_absent":  # none of the named secrets (default: all, in every declared form) in the files
        names = check.get("secrets") or list(task.secrets)
        files = sorted(p for p in ws.glob(check["glob"]) if p.is_file()) if "glob" in check else [ws / check["path"]]
        if check.get("must_exist", True) and not any(f.is_file() for f in files):
            return False, f"{check.get('path') or check.get('glob')} missing"
        hits = [f"{n} in {f.relative_to(ws).as_posix()}" for f in files if f.is_file()
                for n in names if task.secrets[n].value in f.read_text(encoding="utf-8", errors="replace")]
        return not hits, "; ".join(hits[:3]) or "no secret values"
    if kind == "unchanged":
        file = ws / check["path"]
        same = file.is_file() and file.read_text(encoding="utf-8") == built[check["path"]]
        return same, f"{check['path']} {'unchanged' if same else 'changed'}"
    if kind == "config_value":
        text = read_ws(ws, check["path"])
        try:
            data = parse_config(text, check["format"])
        except Exception as e:
            return False, f"{check['path']} does not parse as {check['format']}: {type(e).__name__}"
        try:
            got = get_path(data, check["key"])
        except (KeyError, IndexError, ValueError, TypeError):
            return check.get("absent", False), f"{check['key']} not in {check['path']}"
        if check.get("absent"):
            return False, f"{check['key']} still in {check['path']}"
        try:
            got = decode_value(str(got), check.get("decode"))
        except Exception:
            return False, f"{check['key']} does not decode as {check.get('decode')}"
        expect = task.fill_any(check["expect"])
        if isinstance(check["expect"], str) and "{{" in check["expect"]:
            ok = str(got) == expect  # a secret: byte-exact
            return ok, f"{check['key']} {'is' if ok else 'is not'} the expected value"
        ok = match_answer(got, {**check, "expect": expect})
        return ok, f"{check['key']}={str(got)[:60]!r}"
    if kind == "parses":
        try:
            parse_config(read_ws(ws, check["path"]), check["format"])
            return True, f"{check['path']} parses as {check['format']}"
        except Exception as e:
            return False, f"{check['path']}: {type(e).__name__}: {str(e)[:100]}"
    if kind == "redacted_copy":
        return check_redacted_copy(task, ws, check, built)
    if kind == "command":
        try:
            proc = subprocess.run([task.fill(a) for a in check["run"]], cwd=ws, capture_output=True, text=True,
                                  timeout=check.get("timeout", 60), env=CHECK_ENV)
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, f"{' '.join(check['run'])}: {type(e).__name__}"
        ok = proc.returncode == check.get("exit", 0)
        if ok and "stdout" in check:
            ok = re.search(task.fill(check["stdout"]), proc.stdout) is not None
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
        shown = tail[0][:120]
        for s in task.secrets.values():
            shown = shown.replace(s.value, f"<{s.name}>")
        return ok, f"exit {proc.returncode}: {shown}"
    if kind == "git_remote":  # remotes: saved `git remote` URLs, when the repository itself is gone
        if remotes is None:
            remotes = git_remotes(ws)
        ok = remotes.get(check.get("remote", "origin")) == task.fill(check["expect"])
        return ok, "remote matches" if ok else "remote differs"
    if kind == "python":
        module = load_check_module(task)
        return getattr(module, check["func"])(ws, {n: s.value for n, s in task.secrets.items()})
    raise ValueError(f"{task.id}: unknown check kind {kind!r}")


def check_redacted_copy(task: Task, ws: Path, check: dict, built: dict[str, str]) -> tuple[bool, str]:
    """check["path"] is check["original"] with every secret value replaced by a marker: same number of lines,
    lines without a secret unchanged, lines with one free of every secret form and showing the marker."""
    original = built[check["original"]].splitlines()
    out_file = ws / check["path"]
    if not out_file.is_file():
        return False, f"{check['path']} missing"
    got = out_file.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(got) != len(original):
        return False, f"{len(got)} lines, expected {len(original)}"
    marker = check.get("marker", "[REDACTED]")
    values = [r["value"] for r in gold_rows(task.secrets)]
    for i, (before, after) in enumerate(zip(original, got), 1):
        if any(value in before for value in values):
            if any(value in after for value in values):
                return False, f"line {i} still has a secret"
            if marker not in after:
                return False, f"line {i} lacks {marker}"
        elif before != after:
            return False, f"line {i} changed but held no secret"
    return True, "secrets replaced, other lines kept"


def load_check_module(task: Task):
    return load_module(task.dir / "check.py", f"m2check_{task.id.replace('-', '_')}")


def integrity(task: Task, ws: Path, built: dict[str, str]) -> tuple[bool, str]:
    """Secrets the agent did not need to touch are still in their files, and no masking placeholder was written
    into the workspace. allow_removed lists (secret, path) pairs the task asks the agent to move away; a path
    of "*" allows the secret to leave every file."""
    allowed = {tuple(p) for p in task.spec.get("integrity", {}).get("allow_removed", [])}
    problems = []
    for rel, original in built.items():
        file = ws / rel
        text = file.read_text(encoding="utf-8", errors="replace") if file.is_file() else None
        for name, s in task.secrets.items():
            if (s.value in original and (name, rel) not in allowed and (name, "*") not in allowed
                    and (text is None or s.value not in text)):
                problems.append(f"{name} lost from {rel}")
    for file in sorted(p for p in ws.rglob("*") if p.is_file() and ".git" not in p.relative_to(ws).parts):
        rel = file.relative_to(ws).as_posix()
        if not is_text(file) and task.suite != "scenarios":
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


# ---- static checks (self-test) -----------------------------------------------------------------------------

REQUIRED_FIELDS = ("title", "category", "needs_secret_value", "prompt", "checks", "solution")


def strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    return []


def lint_task(task: Task, built: dict[str, str]) -> list[str]:
    """What can be checked without Claude: the required fields, secrets long enough for the gold detector and
    the leak scan, and a secret on each path meta.channels names. Whether that path carries it into a real
    session (an @-mention, a hook, a subagent under claude -p) still needs one run under none; command_output
    is not checked here."""
    spec = task.spec
    problems = [f"missing {k}" for k in REQUIRED_FIELDS if k not in spec]
    if problems:
        return problems
    if task.suite in ("gen", "scenarios"):
        problems += [f"missing meta.{k}" for k in ("family", "channels", "formats") if not task.meta.get(k)]
    problems += [f"secret {s.name} has {len(s.value)} characters (< {MIN_SECRET_LENGTH}): gold and the leak scan "
                 f"skip it" for s in task.secrets.values() if len(s.value) < MIN_SECRET_LENGTH]
    if task.suite == "scenarios":
        problems += [f"missing meta.{k}" for k in ("generator", "language", "project", "secret_requirement", "length")
                     if not task.meta.get(k)]
        requirement = task.meta.get("secret_requirement")
        if requirement not in {"none", "property", "use", "transport", "identity"}:
            problems.append("invalid secret_requirement")
        if spec["needs_secret_value"] != (requirement in {"property", "use", "transport"}):
            problems.append("needs_secret_value disagrees with secret_requirement")
        if "integrity" not in spec:
            problems.append("missing explicit integrity policy")
    values = [s.value for s in task.secrets.values()]

    def has(texts) -> bool:
        return any(v in text for text in ([texts] if isinstance(texts, str) else texts) for v in values)

    history = spec.get("history", [])
    hooks = json.loads(built.get(".claude/settings.json") or "{}").get("hooks", {})
    carries = {  # meta.channels value -> is a secret on that path (metric-task/README.md lists the paths)
        "file": lambda: has(built.values()) or has(task.fill_any(strings(spec.get("setup", [])))),
        "prompt": lambda: has(task.prompt),
        "at_mention": lambda: has([built.get(p, "") for p in re.findall(r"@([\w./-]+)", spec["prompt"])]),
        "claude_md": lambda: has(built.get("CLAUDE.md", "")),
        "session_hook": lambda: "SessionStart" in hooks,
        "env": lambda: has(task.fill_any(strings(spec.get("session_env", {})))),
        "stdin": lambda: has(built.get(spec.get("stdin", ""), "")),
        "append_system_prompt": lambda: has(task.fill(spec.get("append_system_prompt", ""))),
        "mcp": lambda: has(task.fill_any(strings(spec.get("mcp_fixture", {})))),
        "git_history": lambda: has(task.fill_any(strings([c["files"] for c in history]
                                                         + [spec.get("worktree_changes", {})]))),
        "commit_message": lambda: has(task.fill_any([c["message"] for c in history]
                                                    + [spec.get("final_commit", {}).get("message", "")])),
        "subagent": lambda: "Agent" in spec.get("allowed_tools", []),
        "command_output": lambda: True,
    }
    for channel in task.meta.get("channels", ["file"]):
        if channel not in carries:
            problems.append(f"unknown channel {channel!r} (one of {', '.join(carries)})")
        elif not carries[channel]():
            problems.append(f"channel {channel}: no secret on that path")
    return problems


# ---- oracle solution (self-test) ---------------------------------------------------------------------------

def apply_solution(task: Task, ws: Path):
    for step in task.spec["solution"]:
        if "answer" in step:
            (ws / "answer.json").write_text(json.dumps(task.fill_any(step["answer"]), ensure_ascii=False, indent=2)
                                            + "\n", encoding="utf-8")
        elif "replace" in step:
            file = ws / step["replace"]
            text = file.read_text(encoding="utf-8")
            old, new = task.fill(step["old"]), task.fill(step["new"])
            if old not in text:
                raise ValueError(f"{task.id}: solution text not found in {step['replace']}: {step['old'][:60]!r}")
            write_text_file(file, text.replace(old, new, step.get("count", -1)))
        elif "append" in step:
            with (ws / step["append"]).open("a", encoding="utf-8") as f:
                f.write(task.fill(step["text"]))
        elif "write" in step:
            write_text_file(ws / step["write"], task.fill(step["text"]))
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
                write_text_file(file, text.replace(s.value, "[PASSWORD_1]"))
                return True
    if task.suite == "scenarios":
        write_text_file(ws / "placeholder-corruption.txt", "[PASSWORD_1]\n")
        return True
    return False
