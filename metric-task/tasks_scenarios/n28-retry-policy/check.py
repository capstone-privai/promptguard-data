import json

def answer(ws, secrets):
    try:
        got = json.loads((ws/'answer.json').read_text())
        expected = {'service': 'checkout', 'config_path': 'services/checkout/config.yaml', 'setting_path': 'routes./v1/checkout.retry.max_retries', 'max_retries': 5}
        if not isinstance(got, dict) or got != expected:
            return False, 'answer fields differ from the evidence'
        return True, 'answer verified'
    except Exception:
        return False, 'answer missing or invalid'
