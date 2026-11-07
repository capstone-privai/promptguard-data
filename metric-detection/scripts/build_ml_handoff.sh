#!/usr/bin/env bash
# Rebuild the ML training handoff ("0단계") from the repository and privesc-llm-data, then check the sha256 of every
# data file against metric-detection/templates/ml_train/handoff_step0.json. No API is called.
#
# Run from anywhere inside the repository:
#   bash metric-detection/scripts/build_ml_handoff.sh            # all steps
#   bash metric-detection/scripts/build_ml_handoff.sh STEP ...   # download | build | privesc | export | check
# Environment:
#   PRIVESC_DIR  local copy of sailab-vienna/privesc-llm-data (default: <repo>/../privesc-llm-data); downloaded with
#                the hf CLI (pip install huggingface_hub) at the pinned revision if missing
#   PYTHON       python 3.11+ with datasketch==2.0.0 (default: python3)
# Writes metric-detection/ml_build/ (inputs), metric-detection/ml_handoff/ (train, val), and data_test/,
# data_answer/, labels_mleval_*, manifest_mleval.json (test, test_ood). All of it is git-ignored: fake credentials in
# real formats and privesc's SSH keys. Do not commit or share it publicly.
set -euo pipefail

REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO"
PY="${PYTHON:-python3}"
MD=metric-detection
S=$MD/scripts
ML=$MD/templates/ml_train
OUT=$MD/ml_build
PRIVESC_DIR="${PRIVESC_DIR:-$REPO/../privesc-llm-data}"
REVISION=39a9d2ff37222184fcaf2a6d9a124906e8bb49ad   # convert_privesc.REVISION
TEMPLATES=(v1 hand_v1)   # raw/v1_local.jsonl (Twilio SID templates) is not in git and is left out

step_download() {
  if [ -d "$PRIVESC_DIR/paper_sft_dataset" ]; then
    echo "privesc-llm-data: $PRIVESC_DIR"
    return
  fi
  hf download sailab-vienna/privesc-llm-data --repo-type dataset --revision "$REVISION" --local-dir "$PRIVESC_DIR"
}

step_build() {
  for t in "${TEMPLATES[@]}"; do
    "$PY" $S/ml_train_build.py build $ML/$t.jsonl --out $OUT
    "$PY" $S/ml_train_build.py verify $OUT/data_test/sessions_ml_$t.jsonl | tail -n 3
  done
}

synthetic_train_gold() {
  "$PY" - "$OUT" "${TEMPLATES[@]}" <<'EOF'
import json, sys
out, names = sys.argv[1], sys.argv[2:]
n = 0
for name in names:
    split = {json.loads(l)["session_id"]: json.loads(l)["meta"]["split"]
             for l in open(f"{out}/data_test/sessions_ml_{name}.jsonl", encoding="utf-8")}
    n += sum(split[json.loads(l)["session_id"]] == "train"
             for l in open(f"{out}/data_answer/gold_ml_{name}.jsonl", encoding="utf-8"))
print(n)
EOF
}

step_privesc() {
  local gold
  gold="$(synthetic_train_gold)"
  echo "synthetic train gold: $gold"
  "$PY" $S/ml_train_privesc.py build --privesc "$PRIVESC_DIR" --out $OUT --synthetic-train-gold "$gold" > /dev/null
  "$PY" $S/ml_train_privesc.py verify --privesc "$PRIVESC_DIR" --out $OUT --synthetic-train-gold "$gold" \
    | grep -E '"(train_gold_share|labeling|masks|reproduction)"'
}

step_export() {
  "$PY" $S/ml_train_export.py $OUT/data_test/sessions_ml_v1.jsonl $OUT/data_test/sessions_ml_hand_v1.jsonl \
    $OUT/data_test/sessions_ml_privesc.jsonl
}

step_check() {
  "$PY" $S/ml_train_handoff.py check
}

steps=("$@")
[ ${#steps[@]} -eq 0 ] && steps=(download build privesc export check)
for s in "${steps[@]}"; do
  echo "== $s"
  "step_$s"
done
