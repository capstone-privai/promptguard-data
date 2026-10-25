"""Which purposes each kind of session may be used for.

Every session carries meta.origin and meta.allowed_use. allowed_use is derived from origin and
meta.split (allowed_use below) here and nowhere else; dataset_verify.py rejects sessions whose
allowed_use differs.

  authored  secrets written where they naturally belong (built-in corpus, authored templates)
  recorded  real agent runs whose secrets were planted in the environment before the run
  injected  secrets pushed into a trajectory that was not written for them; the context does
            not match the secret, so an ML filter would learn the injection, not the secret
  external  third-party benchmark (CredData); evaluation only, never training

Code that consumes sessions should call require_use(sessions, purpose) before using them.

ml_eval includes CredSweeper with ML validation enabled (--ml on).
"""
from __future__ import annotations

USES = ("rule_eval", "ml_eval", "ml_train")

ALLOWED_USE = {
    "authored": ["rule_eval", "ml_eval", "ml_train"],
    "recorded": ["rule_eval", "ml_eval", "ml_train"],
    "injected": ["rule_eval"],
    "external": ["rule_eval", "ml_eval"],
}

# Splits of the ML training data (ml_train_build.py, ml_train_export.py): a session on the training side is never
# scored, and a held-out one is never trained on. Other split names (privesc's upstream training and validation,
# Nemotron's test) are not these: their sessions keep ALLOWED_USE[origin] as before.
TRAIN_SPLITS = ("train", "val")
EVAL_SPLITS = ("test", "test_ood")


def allowed_use(origin: str, split: str | None = None) -> list[str]:
    uses = ALLOWED_USE[origin]
    if split in TRAIN_SPLITS:
        return [u for u in uses if u == "ml_train"]
    if split in EVAL_SPLITS:
        return [u for u in uses if u != "ml_train"]
    return uses


def require_use(sessions: list[dict], purpose: str):
    """Raise if any session may not be used for purpose."""
    if purpose not in USES:
        raise ValueError(f"unknown purpose {purpose!r}, expected one of {USES}")
    denied = [s["session_id"] for s in sessions if purpose not in s["meta"].get("allowed_use", [])]
    if denied:
        raise PermissionError(f"{len(denied)} session(s) not allowed for {purpose}: {denied[:5]}")
