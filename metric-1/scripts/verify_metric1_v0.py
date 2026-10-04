"""Verify injection provenance and optionally scan clean carriers.

Run from the repo root: python metric-1/scripts/verify_metric1_v0.py --evaluation-repo ../promptguard-demo-v0 [--scan-carriers]
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import sys

from build_metric1_v0 import build, validate, write_jsonl


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--scan-carriers", action="store_true")
    parser.add_argument("--evaluation-repo", type=Path, required=True, help="Path to promptguard-demo-v0 with the evaluation package")
    args = parser.parse_args()
    evaluation_repo = args.evaluation_repo.resolve()
    if not (evaluation_repo / "evaluation/dataset/validate.py").is_file():
        parser.error("--evaluation-repo must contain evaluation/dataset/validate.py")
    sys.path.insert(0, str(evaluation_repo))
    from evaluation.dataset.validate import validate_dataset
    root = args.dataset_dir
    issues = validate_dataset(root / "sessions.jsonl")
    if issues:
        raise ValueError("\n".join(map(str, issues)))
    corpus = build()
    validate(corpus)
    # Rebuild independently, compare exact UTF-8 bytes including embedded CRLF.
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        for filename, rows in (("sessions.jsonl", corpus.sessions), ("annotations.jsonl", corpus.annotations),
                               ("carrier_review.jsonl", corpus.bases), ("item_provenance.jsonl", corpus.operations)):
            write_jsonl(temp / filename, rows)
            if (temp / filename).read_bytes() != (root / filename).read_bytes():
                raise ValueError(f"Non-reproducible or edited file: {filename}")
    digest = hashlib.sha256((root / "sessions.jsonl").read_bytes()).hexdigest()
    if digest != json.loads((root / "manifest.json").read_text())["dataset_sha256"]:
        raise ValueError("Dataset hash does not match manifest")
    result = {"schema": "passed", "insertion_spans_and_all_long_value_occurrences": "passed",
              "mask_keep_disjoint": "passed", "byte_reproduction": "passed", "sha256": digest}
    if args.scan_carriers:
        from evaluation.adapters.credsweeper_adapter import CredSweeperAdapter
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        for a in corpus.annotations:
            if a["type"] == "PRIVATE_KEY":
                load_pem_private_key(a["value"].encode(), password=None)
        result["private_key_format"] = "valid PKCS8; deterministic offline test key"
        scanner = CredSweeperAdapter()
        findings = []
        negative_values = {a["value"]: a["reason"] for a in corpus.annotations if a["action"] == "KEEP"}
        reviewed_context = {
            ("m1-01-node-env/03", "42:9"): "stack_trace_line_and_column",
            ("m1-03-compose/02", "8:const"): "rg_line_number_and_source_keyword",
            ("m1-03-compose/02", "9:const"): "rg_line_number_and_source_keyword",
            ("m1-11-negative-config/02", "8192"): "max_tokens_count",
        }
        for item in corpus.bases:
            for start, end in scanner.detect(item["text"]):
                detected = item["text"][start:end]
                disposition = ("removed_injection_slot" if detected == "<REDACTED>" else
                    negative_values.get(detected) or reviewed_context.get((item["item_id"], detected)) or "needs_review")
                findings.append({"item_id": item["item_id"], "start": start, "end": end,
                                 "value": detected, "agent_review": disposition})
        carrier_result = {"scanner": "CredSweeper 1.18.5, ML off",
            "scope": "Authored carrier text; MASK slots replaced by <REDACTED>, KEEP slots retained",
            "findings": findings, "human_review": "pending"}
        (root / "carrier_scan.json").write_text(json.dumps(carrier_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["carrier_scan_findings"] = len(findings)
        result["unresolved_carrier_findings"] = sum(f["agent_review"] == "needs_review" for f in findings)
    (root / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
