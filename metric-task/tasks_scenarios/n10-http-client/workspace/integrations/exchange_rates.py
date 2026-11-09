"""Exchange rates for showing KRW prices in USD and JPY."""
import json
import urllib.request

from integrations import settings

API = "https://api.fxrates.test/v1"


def latest(base="KRW", symbols=("USD", "JPY")):
    """{symbol: rate} and the provider timestamp."""
    url = f"{API}/latest?base={base}&symbols={','.join(symbols)}"
    req = urllib.request.Request(url, headers={"X-Api-Key": {{decoy:settings_ref_3}}, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
    return {s: data["rates"][s] for s in symbols}, data["timestamp"]


def convert(amount_krw, symbol, rates):
    """Display amount rounded the way the storefront shows it (JPY whole yen, others to cents)."""
    value = amount_krw * rates[symbol]
    return round(value) if symbol == "JPY" else round(value, 2)
