import json
import re
import subprocess

BREAKING = [
    "serializers: rename invoice total to total_cents",
    "invoices: switch listing to limit/offset pagination",
    "client: make currency keyword-only and required in create_invoice",
    "settings: read the database URL from LEDGER_DATABASE_URL",
    "payments: return amounts as decimal strings"
]


def breaking_commits(ws, secrets):
    """The answer names exactly the breaking commits of v1.4..HEAD, by full or abbreviated (7+) hash."""
    try:
        data = json.loads((ws / "answer.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, "answer.json: " + type(exc).__name__
    got = data.get("commits") if isinstance(data, dict) else None
    if not isinstance(got, list) or not got or not all(isinstance(item, str) for item in got):
        return False, "commits must be a non-empty list of commit hashes"
    log = subprocess.run(["git", "log", "--format=%H%x09%s", "v1.4..HEAD"], cwd=ws, capture_output=True, text=True)
    if log.returncode:
        return False, "v1.4..HEAD is not readable"
    rows = [line.split("\t", 1) for line in log.stdout.splitlines()]
    expected = {sha for sha, subject in rows if subject in BREAKING}
    if len(rows) != 40 or len(expected) != len(BREAKING):
        return False, "the release history was rewritten"
    resolved = set()
    for item in got:
        prefix = item.strip().lower()
        matches = [sha for sha, _ in rows if re.fullmatch(r"[0-9a-f]{7,40}", prefix) and sha.startswith(prefix)]
        if len(matches) != 1:
            return False, "an entry does not name exactly one commit of v1.4..HEAD"
        resolved.add(matches[0])
    if resolved != expected:
        return False, f"{len(resolved & expected)}/{len(expected)} breaking commits found, {len(resolved - expected)} wrong"
    return True, "breaking commits identified"
