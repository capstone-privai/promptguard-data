"""Values the evaluation side spells out on its own must match the data scripts and the system."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

from evaluation.adapters.promptguard_adapter import CHANNEL_MAP, ModFailure, ModSession
from evaluation.adapters.system_root import MOD, load_worker
from evaluation.dataset.io import load_sessions
from evaluation.dataset.schema import CHANNELS, GOLD_TYPES, USES
from evaluation.tests.support import GOLD, HAS_PROMPTGUARD, SESSIONS, SYSTEM_ROOT, finding, found

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
NODE = shutil.which("node")

# Loads a fresh copy of register.mjs per session (its placeholder ledger is module state) and runs each text
# through its prompt.submit hook, with the detector call answered by the given worker result.
NODE_DRIVER = """
import { pathToFileURL } from 'node:url'
let raw = ''
for await (const chunk of process.stdin) raw += chunk
const { mod, sessions } = JSON.parse(raw)
const out = []
for (const [index, steps] of sessions.entries()) {
  const handlers = {}
  ;(await import(pathToFileURL(mod).href + '?session=' + index)).register((name, ...rest) => { handlers[name] = rest.at(-1) })
  const texts = []
  for (const { text, result } of steps) {
    const $ = {
      env: { get: async () => undefined },
      fs: { write: async () => {} },
      mcp: { call: async (_server, _tool, { items }) => ({ isError: false, content: [{ type: 'text',
        text: JSON.stringify({ ok: Boolean(result.ok), items: items.map(item => ({ id: item.id, ...result })) }) }] }) },
    }
    try { texts.push((await handlers['prompt.submit']($, { text }, async e => e)).text) } catch { texts.push(null) }
  }
  out.push(texts)
}
process.stdout.write(JSON.stringify(out))
"""


class DataContractTests(unittest.TestCase):
    def test_channels_and_types_match_dataset_build(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            import dataset_build
        finally:
            sys.path.remove(str(SCRIPTS))
        self.assertEqual(set(CHANNELS), dataset_build.CHANNELS)
        self.assertEqual(set(GOLD_TYPES), dataset_build.TYPES)

    def test_gitleaks_scans_promptguards_channels_by_default(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            import run_gitleaks
        finally:
            sys.path.remove(str(SCRIPTS))
        self.assertEqual(run_gitleaks.PROMPTGUARD_CHANNELS.split(","), list(CHANNEL_MAP))

    def test_evaluation_uses_match_dataset_policy(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            import dataset_policy
        finally:
            sys.path.remove(str(SCRIPTS))
        self.assertEqual(set(USES), set(dataset_policy.USES) - {"ml_train"})
        self.assertEqual(set(dataset_policy.USES), {"rule_eval", "ml_eval", "ml_train"})
        for origin in ("authored", "recorded", "external"):
            dataset_policy.require_use([{"session_id": origin, "meta": {
                "allowed_use": dataset_policy.ALLOWED_USE[origin]}}], "ml_eval")
        with self.assertRaises(PermissionError):
            dataset_policy.require_use([{"session_id": "injected", "meta": {
                "allowed_use": dataset_policy.ALLOWED_USE["injected"]}}], "ml_eval")


def _python_texts(steps: list[dict[str, Any]]) -> list[str | None]:
    mod, texts = ModSession(), []
    for step in steps:
        try:
            texts.append(mod.redact(step["text"], step["result"])[0])
        except ModFailure:
            texts.append(None)
    return texts


def _scripted_sessions() -> list[list[dict[str, Any]]]:
    overlap, after = "key=abcdefgh\n", "other=zzzzzzzz\n"
    emoji = "😀 token=abcdefgh and 🔐 again abcdefgh\n"
    repeated = "A=Qw3rTy9uIo B=Zx8cVb7nMm\n"
    return [
        [{"text": overlap, "result": found(finding(overlap, "abcdef", value_hash="a"), finding(overlap, "efgh"))},
         {"text": after, "result": found(finding(after, "zzzzzzzz"))}],
        [{"text": emoji, "result": found(finding(emoji, "abcdefgh", "TOKEN"), finding(emoji, "abcdefgh", "TOKEN", nth=1))},
         {"text": repeated, "result": found(finding(repeated, "Zx8cVb7nMm"), finding(repeated, "Qw3rTy9uIo"),
                                            finding(repeated, "A", "api key"))}],
        [{"text": overlap, "result": found(finding(overlap, "abcd", offset_unit="code_points"))},
         {"text": overlap, "result": found(finding(overlap, "abcd", end=99))},
         {"text": overlap, "result": {"ok": False, "findings": [], "errors": ["SPAN_TOO_LARGE"]}},
         {"text": overlap, "result": {"ok": True, "findings": [], "errors": ["INVALID_OFFSET_RANGE"]}},
         {"text": overlap, "result": found(finding(overlap, "abcd"))}],
    ]


def _worker_sessions() -> list[list[dict[str, Any]]]:
    detector = load_worker(SYSTEM_ROOT).Adapter()
    sessions = [[{"text": item.text, "result": detector.scan(item.text, CHANNEL_MAP[item.channel])}
                 for item in session.items if item.channel in CHANNEL_MAP]
                for session in load_sessions(SESSIONS, GOLD)]
    extra = ["🔐 DB_PASSWORD=mysecret123\n", "A_PASSWORD=Qw3rTy9uIo\nB_PASSWORD=Zx8cVb7nMm\nA_PASSWORD=Qw3rTy9uIo\n"]
    return sessions + [[{"text": text, "result": detector.scan(text, "tool_result")} for text in extra]]


@unittest.skipIf(SYSTEM_ROOT is None, "no promptguard-claude-demoV0 checkout")
class ModContractTests(unittest.TestCase):
    def test_channel_map_uses_the_mods_sources(self) -> None:
        mod = (SYSTEM_ROOT / MOD).read_text(encoding="utf-8")
        self.assertLessEqual(set(CHANNEL_MAP), set(CHANNELS))
        for source in CHANNEL_MAP.values():
            self.assertIn(f"'{source}'", mod)

    @unittest.skipIf(NODE is None, "node is not installed")
    def test_redaction_matches_register_mjs(self) -> None:
        sessions = _scripted_sessions() + (_worker_sessions() if HAS_PROMPTGUARD else [])
        done = subprocess.run([NODE, "--input-type=module", "-e", NODE_DRIVER], capture_output=True, text=True,
                              input=json.dumps({"mod": str(SYSTEM_ROOT / MOD), "sessions": sessions}), timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        expected = json.loads(done.stdout)
        self.assertEqual([_python_texts(steps) for steps in sessions], expected)
        self.assertNotIn(None, expected[1])  # valid findings were substituted
        self.assertIn(None, expected[2])  # the failure cases did fail


if __name__ == "__main__":
    unittest.main()
