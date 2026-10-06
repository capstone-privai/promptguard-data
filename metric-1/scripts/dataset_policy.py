"""Which purposes each kind of session may be used for.

Every session carries meta.origin and meta.allowed_use. allowed_use is derived from origin
here and nowhere else; verify_dataset.py rejects sessions whose allowed_use differs.

  authored  secrets written where they naturally belong (built-in corpus, authored templates)
  recorded  real agent runs whose secrets were planted in the environment before the run
  injected  secrets pushed into a trajectory that was not written for them; the context does
            not match the secret, so an ML filter would learn the injection, not the secret
  external  third-party benchmark (CredData); evaluation only, never training

Code that consumes sessions should call require_use(sessions, purpose) before using them.
"""
from __future__ import annotations

USES = ("rule_eval", "ml_eval", "ml_train")

ALLOWED_USE = {
    "authored": ["rule_eval", "ml_eval", "ml_train"],
    "recorded": ["rule_eval", "ml_eval", "ml_train"],
    "injected": ["rule_eval"],
    "external": ["rule_eval", "ml_eval"],
}


def require_use(sessions: list[dict], purpose: str):
    """Raise if any session may not be used for purpose."""
    if purpose not in USES:
        raise ValueError(f"unknown purpose {purpose!r}, expected one of {USES}")
    denied = [s["session_id"] for s in sessions if purpose not in s["meta"].get("allowed_use", [])]
    if denied:
        raise PermissionError(f"{len(denied)} session(s) not allowed for {purpose}: {denied[:5]}")
