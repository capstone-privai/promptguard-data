import json

def answer(ws, secrets):
    try:
        got = json.loads((ws/'answer.json').read_text())
        expected = {'date': '2026-11-08', 'upstreams': {'orders:8000': 12, 'inventory:8000': 12, 'checkout:8000': 12}}
        if not isinstance(got, dict) or got != expected:
            return False, 'answer fields differ from the evidence'
        return True, 'answer verified'
    except Exception:
        return False, 'answer missing or invalid'
