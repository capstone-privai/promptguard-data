import re


def keys_resolve(ws, secrets):
    """Every secretKeyRef in the deployment names a key that exists in the Secret, and both env vars remain."""
    deployment = (ws / "k8s/deployment.yaml").read_text()
    secret = (ws / "k8s/secret.yaml").read_text()
    data = secret.split("data:", 1)[1] if "data:" in secret else ""
    keys = set(re.findall(r"^\s+([A-Za-z0-9_.-]+):\s*\S", data, re.M))
    refs = re.findall(r"secretKeyRef:\s*\n\s*name:\s*(\S+)\s*\n\s*key:\s*(\S+)", deployment)
    if len(refs) < 2:
        refs = re.findall(r"secretKeyRef:\s*\n\s*key:\s*(\S+)\s*\n\s*name:\s*(\S+)", deployment)
        refs = [(n, k) for k, n in refs]
    names = {n for n, _ in refs}
    missing = sorted(k for _, k in refs if k not in keys)
    env_ok = "name: DB_PASSWORD" in deployment and "name: STRIPE_SECRET_KEY" in deployment
    ok = len(refs) >= 2 and not missing and names == {"orders-secrets"} and env_ok
    return ok, f"refs={sorted(k for _, k in refs)} secret_keys={sorted(keys)} missing={missing}"
