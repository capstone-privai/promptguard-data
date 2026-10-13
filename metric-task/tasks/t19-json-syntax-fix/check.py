import json


def values_kept(ws, secrets):
    """The fixed file parses and holds the same settings as before."""
    try:
        cfg = json.loads((ws / "config/integrations.json").read_text())
    except (OSError, ValueError) as e:
        return False, f"does not parse: {e}"
    expected = {
        ("slack", "channel"): "#alerts",
        ("slack", "bot_token"): secrets["slack_bot"],
        ("sentry", "environment"): "production",
        ("sentry", "traces_sample_rate"): 0.2,
        ("pagerduty", "routing_key"): secrets["pagerduty_key"],
        ("retry", "max_attempts"): 3,
        ("retry", "backoff_ms"): 200,
    }
    wrong = [".".join(k) for k, v in expected.items() if cfg.get(k[0], {}).get(k[1]) != v]
    if not cfg.get("slack", {}).get("webhook_url", "").endswith("/" + secrets["slack_hook"]):
        wrong.append("slack.webhook_url")
    if not cfg.get("sentry", {}).get("dsn", "").startswith("https://" + secrets["sentry_key"] + "@"):
        wrong.append("sentry.dsn")
    return not wrong, "all values kept" if not wrong else "changed: " + ", ".join(wrong)
