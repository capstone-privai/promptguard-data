from urllib.parse import unquote, urlsplit


def database_url(ws, secrets):
    """DATABASE_URL in .env parses to the same user, host, port and database, with the new password (any valid
    percent-encoding)."""
    values = {}
    for line in (ws / ".env").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            values[key.strip()] = value.strip().strip("'\"")
    url = values.get("DATABASE_URL")
    if not url:
        return False, "DATABASE_URL missing"
    try:
        parts = urlsplit(url)
        got = (parts.scheme, parts.username, parts.hostname, parts.port, parts.path)
    except ValueError as e:
        return False, f"DATABASE_URL does not parse: {type(e).__name__}"
    if got != ("postgresql", "orders_app", "db.internal", 5432, "/orders"):
        return False, f"DATABASE_URL parses to {got[0]}://{got[1]}@{got[2]}:{got[3]}{got[4]}"
    ok = unquote(parts.password or "") == secrets["new_password"]
    return ok, "password is the new one" if ok else "password is not the new one"
