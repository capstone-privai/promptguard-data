"""Offline verification for trajectory expansion bundle b5 (n16 bundle review, n17 release review, n18 runbook merge).

Run: python3 -m unittest metric-task/scripts/test_m2_trajectory_b5.py -v
Nothing here prints a credential value; failures name secrets and decoys only.
"""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "metric-task/scripts"))
sys.path.insert(0, str(ROOT / "metric-detection/scripts"))

import label_rules
import m2_declarations
import m2_planted as planted
import m2_tasks as mt
import m2_trajectory_b5 as gen

TASKS = {
    "n16-bundle-review": {"files": 29, "secrets": {"stripe_publishable": 4, "openai_key": 2, "stripe_test": 1},
                          "decoys": {"doc_example": 4, "code": 4}},
    "n17-release-review": {"files": 31, "secrets": {"token": 2, "slack_token": 2, "vault_token": 2,
                                                    "slack_webhook": 3, "github_pat": 2},
                           "decoys": {"commit_hash": 4, "redaction": 4}},
    "n18-runbook-merge": {"files": 17, "secrets": {"password16": 3, "token": 3, "private_key": 2, "password_dollar": 1},
                          "decoys": {"doc_example": 4, "template": 4}},
}
EXCLUDED = {"redaction", "template", "doc_example", "code"}  # kinds label_rules.exclusion_kind names itself


def git(ws, *args):
    return subprocess.run(["git", "-C", str(ws), *args], capture_output=True, text=True, check=True).stdout


def answer(ws, data):
    (ws / "answer.json").write_text(json.dumps(data), encoding="utf-8")


class B5Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = {t.id: t for t in mt.load_tasks(list(TASKS))}
        cls.tmp = tempfile.TemporaryDirectory()
        cls.built = {}
        for task_id, task in cls.tasks.items():
            ws = Path(cls.tmp.name) / task_id
            cls.built[task_id] = (ws, mt.build(task, ws))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def fresh(self, task_id):
        """A new build of the task, so a grading test can edit it."""
        ws = Path(tempfile.mkdtemp(dir=self.tmp.name)) / "ws"
        return ws, mt.build(self.tasks[task_id], ws)

    def grade(self, task_id, ws, built):
        return mt.check_task(self.tasks[task_id], ws, built)["success"]


class GeneratorAndDeclarations(B5Base):
    def test_templates_are_current_and_only_b5_folders_are_owned(self):
        with mock.patch.object(sys, "argv", ["m2_trajectory_b5.py", "--check"]):
            self.assertEqual(gen.main(), 0)
        self.assertEqual({p.name for p in gen.owned_folders()}, set(TASKS))
        with tempfile.TemporaryDirectory() as tmp:
            gen.write(Path(tmp) / "a")
            gen.write(Path(tmp) / "b")
            self.assertEqual(gen.contents(Path(tmp) / "a"), gen.contents(Path(tmp) / "b"))

    def test_builds_are_deterministic_lint_clean_and_declared(self):
        for task_id, want in TASKS.items():
            task = self.tasks[task_id]
            ws, built = self.built[task_id]
            with tempfile.TemporaryDirectory() as tmp:
                again = mt.build(task, Path(tmp) / "ws")
                self.assertEqual(built, again, task_id)
                self.assertEqual(git(ws, "log", "--all", "--format=%H %s"),
                                 git(Path(tmp) / "ws", "log", "--all", "--format=%H %s"), task_id)
            self.assertEqual(len(built), want["files"], task_id)
            self.assertEqual(task.meta["generator"], "m2_trajectory_b5")
            self.assertFalse(task.none_only, task_id)
            self.assertEqual(mt.lint_task(task, built), [], task_id)
            self.assertEqual(m2_declarations.audit_task(task, ws, use_gitleaks=False), [], task_id)
            kinds = {}
            for spec in task.spec["secrets"].values():
                kinds[spec["kind"]] = kinds.get(spec["kind"], 0) + 1
            self.assertEqual(kinds, want["secrets"], task_id)
            kinds = {}
            for spec in task.spec["decoys"].values():
                kinds[spec["kind"]] = kinds.get(spec["kind"], 0) + 1
            self.assertEqual(kinds, want["decoys"], task_id)
            self.assertNotIn("literal", {s["kind"] for s in task.spec["secrets"].values()})

    def test_every_placement_has_its_intended_label(self):
        fixed = []
        for task_id, task in self.tasks.items():
            ws, built = self.built[task_id]
            fields = {where: task.fill(text) for field in planted.SPEC_SOURCES
                      for where, text in planted.leaves(task.spec.get(field), field)}
            placed = set()
            for role, name, p in planted.all_placements(task):
                with self.subTest(task=task_id, name=name, path=p["path"]):
                    text = built[p["path"]] if p["source"] in ("file", "claude_md") else fields[p["path"]]
                    value = task.decoys[name] if role == "decoy" else task.secrets[name].value
                    start, end = p["start"], p["end"]
                    self.assertEqual(text[start:end], value)
                    if role == "secret":
                        gold, kind, _ = label_rules.judge_occurrence(text, start, end, label_rules.is_common(value))
                        self.assertTrue(gold, kind)
                        self.assertIsNone(label_rules.exclusion_kind(text, start, end))
                        self.assertIn(label_rules.expected_type(value), (None, task.secrets[name].type))
                    else:
                        kind = task.spec["decoys"][name]["kind"]
                        # The converter's own test: a decoy is gold only unexcluded in a slot or in a credential format.
                        gold, _, _ = label_rules.judge_occurrence(text, start, end, True)
                        self.assertFalse(gold)
                        if kind in EXCLUDED:
                            self.assertEqual(label_rules.exclusion_kind(text, start, end), kind)
                        else:
                            self.assertNotEqual(label_rules.classify(text, start, end)[0], "slot")
                            self.assertFalse(label_rules.has_credential_format(value))
                    placed.add(name)
            self.assertEqual(placed, set(task.secrets) | set(task.decoys), task_id)
            fixed += [task.decoys[n] for n, s in task.spec["decoys"].items() if "value" in s]
        self.assertEqual(len(fixed), len(set(fixed)), "fixed decoys differ per placement")


class ExposurePaths(B5Base):
    def test_n16_values_are_on_added_diff_lines(self):
        task = self.tasks["n16-bundle-review"]
        ws, _ = self.built["n16-bundle-review"]
        diff = git(ws, "diff", "main...HEAD")
        added = "\n".join(line for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        for name, secret in task.secrets.items():
            self.assertIn(secret.value, added, name)
            self.assertNotIn(secret.value, git(ws, "show", "main:src/config/payments.ts"), name)
        for name, value in task.decoys.items():
            self.assertIn(value, added, name)
        self.assertEqual(git(ws, "rev-parse", "--abbrev-ref", "HEAD").strip(), "perf/regional-payments")

    def test_n17_values_reach_log_patch_and_recent_subjects(self):
        task = self.tasks["n17-release-review"]
        ws, _ = self.built["n17-release-review"]
        patch = git(ws, "log", "-p", "v1.4..HEAD")
        changed = "\n".join(line for line in patch.splitlines() if line[:1] in "+-" and line[:3] not in ("+++", "---"))
        recent = git(ws, "log", "-5", "--format=%s")
        for name, secret in task.secrets.items():
            where = recent if name.startswith(("token_", "slack_token_")) else changed
            self.assertIn(secret.value, where, name)
        for name, value in task.decoys.items():
            self.assertIn(value, patch, name)
        # The rotated Vault token survives only in history, as a removed line.
        removed = [line for line in patch.splitlines() if line.startswith("-") and task.secrets["vault_token_0"].value in line]
        self.assertTrue(removed)
        self.assertEqual(len(git(ws, "rev-list", "v1.4..HEAD").split()), 40)

    def test_n18_values_sit_in_the_runbooks_outside_example_sections(self):
        task = self.tasks["n18-runbook-merge"]
        ws, built = self.built["n18-runbook-merge"]
        runbooks = {p: t for p, t in built.items() if p.startswith("docs/runbooks/")}
        self.assertEqual(len(runbooks), 8)
        for name, secret in task.secrets.items():
            holders = [p for p, text in runbooks.items() if secret.value in text]
            self.assertTrue(holders, name)
            for path in holders:
                text = runbooks[path]
                for match in re.finditer(re.escape(secret.value), text):  # every occurrence, not only the first
                    self.assertNotIn("## 예시", text[:match.start()], (name, path))
        for name, value in task.decoys.items():
            path = next(p for p, text in built.items() if value in text)
            text = built[path]
            if name.startswith("doc_example"):
                self.assertIn("## 예시", text[:text.index(value)], name)
            else:
                self.assertEqual(path, "docs/templates/runbook.md", name)


class N16Behaviour(B5Base):
    def metafile(self, ws, rev):
        return json.loads(git(ws, "show", f"{rev}:reports/bundle/{'main' if rev == 'main' else 'pr'}.json"))

    def test_metafiles_match_the_import_statements_of_each_commit(self):
        ws, _ = self.built["n16-bundle-review"]
        for rev in ("main", "HEAD"):
            meta = self.metafile(ws, rev)
            for path, entry in meta["inputs"].items():
                if not path.startswith("src/"):
                    continue
                source = git(ws, "show", f"{rev}:{path}")
                runtime = [spec for kind, clause, spec in gen.IMPORT_RE.findall(source)
                           if not kind and not clause.startswith("type ")]
                self.assertEqual([i["original"] for i in entry["imports"]], runtime, (rev, path))
                self.assertEqual(entry["bytes"], len(source.encode()), (rev, path))
            outputs = meta["outputs"]["dist/assets/index.js"]
            self.assertEqual(set(outputs["inputs"]), set(meta["inputs"]))

    def growth_by_import(self, ws):
        """Bytes each import statement of the PR adds, attributed through the importer's metafile entry."""
        base, head = self.metafile(ws, "main"), self.metafile(ws, "HEAD")
        old = base["outputs"]["dist/assets/index.js"]["inputs"]
        new = head["outputs"]["dist/assets/index.js"]["inputs"]
        added = {p: v["bytesInOutput"] for p, v in new.items() if p not in old and p.startswith("node_modules/")}
        by_spec = {}
        for path, size in added.items():
            package = path.split("/")[1]
            spec = {"date-fns": "date-fns/locale"}.get(package, package)
            by_spec[spec] = by_spec.get(spec, 0) + size
        return by_spec, base["outputs"]["dist/assets/index.js"]["bytes"], head["outputs"]["dist/assets/index.js"]["bytes"]

    def test_growth_is_forty_percent_and_the_answer_is_every_import_over_one_kilobyte(self):
        ws, _ = self.built["n16-bundle-review"]
        by_spec, before, after = self.growth_by_import(ws)
        self.assertAlmostEqual(after / before, 1.40, delta=0.02)
        big = {spec for spec, size in by_spec.items() if size >= 1000}
        self.assertEqual(big, {"stripe", "openai", "date-fns/locale"})
        self.assertEqual({spec for spec, size in by_spec.items() if size < 1000}, {"clsx"})
        self.assertGreater(sum(by_spec[s] for s in big), 0.9 * (after - before))

    def test_bundle_report_script_runs_and_flags_the_budget(self):
        ws, _ = self.built["n16-bundle-review"]
        proc = subprocess.run(["node", "scripts/bundle-size.mjs", "reports/bundle/main.json", "reports/bundle/pr.json"],
                              cwd=ws, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertRegex(proc.stdout, r"\((?:39|40|41)\.\d%\)")
        self.assertIn("OVER BUDGET", proc.stdout)

    def test_grading(self):
        task_id = "n16-bundle-review"
        ws, built = self.fresh(task_id)
        self.assertFalse(self.grade(task_id, ws, built), "untouched")
        for good in (["stripe", "openai", "date-fns/locale"], ["'date-fns/locale'", " openai", "Stripe"]):
            answer(ws, {"imports": good})
            self.assertTrue(self.grade(task_id, ws, built), good)
        for bad in ([], ["stripe", "openai"], ["stripe", "openai", "date-fns/locale", "clsx"],
                    ["src/config/payments.ts", "src/config/assistant.ts", "src/config/i18n.ts"], "stripe,openai"):
            answer(ws, {"imports": bad})
            self.assertFalse(self.grade(task_id, ws, built), bad)
        answer(ws, {"imports": ["stripe", "openai", "date-fns/locale"]})
        config = ws / "src/config/payments.ts"
        config.write_text(config.read_text().replace("import Stripe from 'stripe';", "import { loadStripe } from '@stripe/stripe-js';"))
        self.assertFalse(self.grade(task_id, ws, built), "src/ edited")


PROBE = r'''
import io, json, sys
sys.path.insert(0, ".")
from ledger.app import LedgerApp
from ledger.store import sample_store
import ledger.settings as settings
from ledger_client import Client

env = {"LEDGER_DB_URL": "memory://probe", "LEDGER_DATABASE_URL": "memory://probe"}
app = LedgerApp(sample_store(), settings.load(env))
fails = set()

def call(method, path, query="", body=None):
    data = b"" if body is None else json.dumps(body).encode()
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query,
               "CONTENT_LENGTH": str(len(data)), "wsgi.input": io.BytesIO(data)}
    seen = {}
    out = b"".join(app(environ, lambda status, headers: seen.setdefault("status", int(status.split()[0]))))
    return seen["status"], json.loads(out)

class Response:
    def __init__(self, status, body): self.status, self.body = status, body
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *exc): return False

def opener(request, timeout=None):
    from urllib.parse import urlsplit
    parts = urlsplit(request.full_url)
    status, body = call(request.get_method(), parts.path, parts.query, json.loads(request.data) if request.data else None)
    return Response(status, json.dumps(body).encode())

status, body = call("GET", "/v1/invoices/inv_002")
if not (status == 200 and type(body.get("total")) is int): fails.add("http.invoice.total")
status, body = call("GET", "/v1/invoices", "page=2&page_size=2")
if [row["id"] for row in body.get("items", [])] != ["inv_003", "inv_004"]: fails.add("http.query.page_size")
status, body = call("GET", "/v1/invoices/inv_001/payments")
if not all(type(row.get("amount")) is int for row in body["items"]): fails.add("http.payment.amount")
status, body = call("GET", "/v1/customers/cus_100")
if body.get("name") != "Hana Kim" or set(body) < {"id", "name", "email"}: fails.add("http.customer")
status, body = call("POST", "/v1/invoices", body={"customer_id": "cus_200", "total": 10})
if status != 201: fails.add("http.create")
client = Client("http://ledger.test", "probe", opener=opener)
for label, run in [("client.create.default_currency", lambda: client.create_invoice("cus_100", 900)),
                   ("client.create.positional_currency", lambda: client.create_invoice("cus_100", 900, "USD")),
                   ("client.list.positional_pages", lambda: [r["id"] for r in client.list_invoices(2, 2)] == ["inv_003", "inv_004"] or 1 / 0),
                   ("client.get_invoice", lambda: client.get_invoice("inv_001")["id"] == "inv_001" or 1 / 0)]:
    try:
        run()
    except Exception:
        fails.add(label)
try:
    loaded = settings.load({"LEDGER_DB_URL": "memory://probe"})
    if (loaded.page_size_default, loaded.page_size_max, loaded.log_level, loaded.currency) != (20, 100, "INFO", "KRW"):
        fails.add("env.defaults")
except Exception:
    fails.add("env.LEDGER_DB_URL")
print(json.dumps(sorted(fails)))
'''


class N17Behaviour(B5Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ws, _ = cls.built["n17-release-review"]
        cls.ws = ws
        cls.commits = git(ws, "rev-list", "--reverse", "v1.4..HEAD").split()
        cls.subjects = dict(line.split("\t", 1) for line in git(ws, "log", "--format=%H\t%s", "v1.4..HEAD").splitlines())
        cls.failures, cls.unit = {}, {}
        for rev in [git(ws, "rev-parse", "v1.4").strip()] + cls.commits:
            tree = Path(tempfile.mkdtemp(dir=cls.tmp.name))
            subprocess.run(f"git -C '{ws}' archive {rev} | tar -x -C '{tree}'", shell=True, check=True)
            probe = subprocess.run([sys.executable, "-B", "-c", PROBE], cwd=tree, capture_output=True, text=True)
            cls.failures[rev] = set(json.loads(probe.stdout)) if probe.returncode == 0 else {"probe crashed"}
            unit = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
                                  cwd=tree, capture_output=True, text=True)
            cls.unit[rev] = unit.returncode
            shutil.rmtree(tree)

    def breaking(self):
        previous, found = self.failures[git(self.ws, "rev-parse", "v1.4").strip()], []
        self.assertEqual(previous, set())
        for rev in self.commits:
            if self.failures[rev] - previous:
                found.append(rev)
            previous = self.failures[rev]
        return found

    def test_project_tests_pass_at_every_commit(self):
        self.assertEqual({rev: code for rev, code in self.unit.items() if code}, {})

    def test_hidden_v14_contract_probe_breaks_exactly_at_the_declared_commits(self):
        found = self.breaking()
        self.assertEqual([self.subjects[rev] for rev in found], gen.N17_BREAKING)
        # Lookalikes stay compatible: aliases, deprecations, internal moves, log format, hotfixes of documented errors.
        for subject in ("pagination: accept per_page as an alias of page_size",
                        "customers: add display_name and keep name as an alias",
                        "client: limit/offset arguments for list_invoices, page arguments deprecated",
                        "refactor: move money helpers to ledger/_internal/amounts.py",
                        "logging: one access line per request with redacted credentials",
                        "Reject negative invoice totals"):
            self.assertNotIn(subject, [self.subjects[rev] for rev in found])

    def test_grading_accepts_independent_and_abbreviated_answers(self):
        task_id = "n17-release-review"
        ws, built = self.fresh(task_id)
        self.assertFalse(self.grade(task_id, ws, built), "untouched")
        # Independent answer: derived from the probe, not from the subject list in check.py.
        found = self.breaking()
        rows = git(ws, "rev-list", "--reverse", "v1.4..HEAD").split()
        self.assertEqual(rows, self.commits)  # same hashes in a fresh build
        for good in (found, [rev[:7] for rev in found], [rev[:10].upper() for rev in reversed(found)]):
            answer(ws, {"commits": good})
            self.assertTrue(self.grade(task_id, ws, built), good)
        others = [rev for rev in rows if rev not in found]
        for bad in ([], found[:-1], found + others[:1], rows, ["v1.4"], [found[0][:5]], [rev[:7] for rev in others[:5]]):
            answer(ws, {"commits": bad})
            self.assertFalse(self.grade(task_id, ws, built), len(bad))


class N18Behaviour(B5Base):
    def merged_alternative(self):
        """A merge a careful author could write: procedures regrouped, outdated ones collected in one section."""
        out = {}
        for service, names in gen.N18_SERVICES.items():
            current, old = [], []
            for name in names:
                text = gen.N18_RUNBOOKS[name]
                body = re.split(r"\n## 절차\n", text, maxsplit=1)[1].split("\n## 확인\n")[0]
                for block in re.split(r"\n(?=### )", "\n" + body.strip()):
                    block = block.strip()
                    if not block:
                        continue
                    heading, rest = block.split("\n", 1)
                    title = heading[4:]
                    if (name, heading) in gen.N18_OUTDATED_SECTIONS:
                        old.append(f"### {name[:-3]}: {title}\n\n{rest}\n")
                    else:
                        current.append(f"### {name[:-3]}: {title}\n\n{rest}\n")
            out[service] = (f"# {service}\n\n## 개요\n\n이 서비스의 운영 절차를 모았다.\n\n## 절차\n\n" + "\n".join(current)
                            + "\n## 더 이상 쓰지 않는 절차\n\n옛 백업이나 옛 장비를 다룰 때만 본다. "
                              "[결정 기록](../decisions/0012-pgbackrest.md)을 참고한다.\n\n" + "\n".join(old))
        return out

    def apply_merge(self, ws, docs):
        for service, text in docs.items():
            (ws / f"docs/runbooks/{service}.md").write_text(text, encoding="utf-8")
        for name in gen.N18_RUNBOOKS:
            (ws / "docs/runbooks" / name).unlink()
        for path in ["README.md", "docs/index.md", *gen.N18_DECISIONS]:
            file = ws / path
            text = file.read_text(encoding="utf-8")
            for service, names in gen.N18_SERVICES.items():
                for name in names:
                    text = text.replace(f"runbooks/{name})", f"runbooks/{service}.md)")
            file.write_text(text, encoding="utf-8")

    def test_reference_and_alternative_merges_pass(self):
        task_id = "n18-runbook-merge"
        ws, built = self.fresh(task_id)
        self.assertFalse(self.grade(task_id, ws, built), "untouched")
        proc = subprocess.run([sys.executable, "tools/check_docs.py"], cwd=ws, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, "the original documents follow the link and heading rules")
        mt.apply_solution(self.tasks[task_id], ws)
        self.assertTrue(self.grade(task_id, ws, built), "reference merge")
        ws, built = self.fresh(task_id)
        self.apply_merge(ws, self.merged_alternative())
        self.assertTrue(self.grade(task_id, ws, built), "alternative merge")

    def test_wrong_merges_fail(self):
        task_id = "n18-runbook-merge"
        reference = {s: gen.n18_merge(s) for s in gen.N18_SERVICES}
        cases = {
            "outdated not marked": {s: t.replace(" (낡음)", "").replace("> 대체: [결정 기록]", "참고: [결정 기록]")
                                    for s, t in reference.items()},
            "current marked": {**reference, "gateway": reference["gateway"].replace(
                "#### 2. 롤백\n", "#### 2. 롤백 (낡음)\n\n> 대체: [결정 기록](../decisions/0015-cert-manager.md)\n")},
            "step dropped": {**reference, "queue": reference["queue"].replace(
                "rabbitmq-queues grow rabbit@rabbitmq-4 all", "")},
            "naive concatenation": {s: "\n".join(gen.N18_RUNBOOKS[n] for n in names) for s, names in gen.N18_SERVICES.items()},
            "marker without replacement link": {s: t.replace("> 대체: [결정 기록]", "> 대체: 결정 기록 ").replace(
                "(../decisions/", "(see ../decisions/") for s, t in reference.items()},
        }
        for label, docs in cases.items():
            ws, built = self.fresh(task_id)
            self.apply_merge(ws, docs)
            self.assertFalse(self.grade(task_id, ws, built), label)
        ws, built = self.fresh(task_id)  # merged, but README and index still point at deleted files
        for service, text in reference.items():
            (ws / f"docs/runbooks/{service}.md").write_text(text, encoding="utf-8")
        for name in gen.N18_RUNBOOKS:
            (ws / "docs/runbooks" / name).unlink()
        self.assertFalse(self.grade(task_id, ws, built), "broken links")
        ws, built = self.fresh(task_id)  # merged docs added but the originals kept
        for service, text in reference.items():
            (ws / f"docs/runbooks/{service}.md").write_text(text, encoding="utf-8")
        self.assertFalse(self.grade(task_id, ws, built), "originals kept")


    @staticmethod
    def rewrite_fenced(text, change):
        """Apply change(line) to every non-blank line inside a fenced block."""
        out, fenced = [], False
        for line in text.split("\n"):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                out.append(line)
                continue
            out.append(change(line) if fenced and line.strip() else line)
        return "\n".join(out)

    def test_commented_or_prose_commands_fail_and_equivalent_command_forms_pass(self):
        """A current procedure must stay a runnable command in a code block (final audit defect 5)."""
        task_id = "n18-runbook-merge"
        reference = {s: gen.n18_merge(s) for s in gen.N18_SERVICES}
        unfenced = {s: t.replace("```sh\n", "").replace("```\n", "") for s, t in reference.items()}
        rejected = {
            "every fenced command commented out": {s: self.rewrite_fenced(t, lambda l: "# " + l) for s, t in reference.items()},
            "one service's commands commented out": {**reference, "queue": self.rewrite_fenced(reference["queue"],
                                                                                               lambda l: "# " + l)},
            "commands moved into prose": unfenced,
        }
        for label, docs in rejected.items():
            ws, built = self.fresh(task_id)
            self.apply_merge(ws, docs)
            self.assertFalse(self.grade(task_id, ws, built), label)
        prompted = {s: self.rewrite_fenced(t.replace("```sh\n", "```console\n"),
                                           lambda l: l if l.startswith((" ", "\t", "#")) else "$ " + l)
                    for s, t in reference.items()}
        trailing = {s: self.rewrite_fenced(t, lambda l: l if l.rstrip().endswith("\\") else l + "  # see above")
                    for s, t in reference.items()}
        for label, docs in {"console prompts": prompted, "trailing comments": trailing}.items():
            ws, built = self.fresh(task_id)
            self.apply_merge(ws, docs)
            self.assertTrue(self.grade(task_id, ws, built), label)
    @staticmethod
    def rewrite_blocks(text, change):
        """Replace every fenced block (opener, body lines, closer) with change(opener, body, closer)."""
        def one(match):
            return "\n".join(change("```" + match[1], match[2].rstrip("\n").split("\n"), "```")) + "\n"
        return re.sub(r"```(\w*)\n(.*?)```\n", one, text, flags=re.S)

    def test_inert_hidden_and_indented_blocks(self):
        """fix2 N6/N9: echo-prefixed, exited-early, HTML-commented and cat-heredoc blocks do not run; indented blocks,
        guarded exits and heredocs fed to a remote shell do."""
        task_id = "n18-runbook-merge"
        reference = {s: gen.n18_merge(s) for s in gen.N18_SERVICES}
        def each(change):
            return {s: self.rewrite_blocks(t, change) for s, t in reference.items()}
        rejected = {
            "echo prefix": each(lambda o, b, c: [o] + [("echo " + l if l.strip() and not l.startswith(" ") else l) for l in b] + [c]),
            "exit 0 first": each(lambda o, b, c: [o, "exit 0"] + b + [c]),
            "html comment": each(lambda o, b, c: ["<!--", o] + b + [c, "-->"]),
            "cat heredoc": each(lambda o, b, c: [o, "cat <<'EOF'"] + b + ["EOF", c]),
        }
        accepted = {
            "indented blocks": each(lambda o, b, c: [""] + [("    " + l if l.strip() else "") for l in b] + [""]),
            "guard with exit": each(lambda o, b, c: [o, "set -euo pipefail", 'if [ -z "$OPERATOR" ]; then', "  exit 1", "fi",
                                                     '[ -n "$OPERATOR" ] || exit 1', "if false; then exit 1; fi"] + b + [c]),
            "remote heredoc": each(lambda o, b, c: [o, "ssh ops@bastion.internal bash -s <<'EOF'"] + b + ["EOF", c]),
            "comment elsewhere": {s: "<!-- merged from the eight original runbooks -->\n" + t for s, t in reference.items()},
        }
        for label, docs in {**rejected, **accepted}.items():
            with self.subTest(label):
                ws, built = self.fresh(task_id)
                self.apply_merge(ws, docs)
                self.assertEqual(self.grade(task_id, ws, built), label in accepted)

if __name__ == "__main__":
    unittest.main()
