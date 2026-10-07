import re


def dotenv_value(text, key):
    """KEY's value in a Compose .env file: single quotes keep $ literal, otherwise $$ stands for $."""
    m = re.search(rf"^{key}=(.*)$", text, re.M)
    if not m:
        return None
    raw = m.group(1).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1]
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        raw = raw[1:-1]
    escaped = raw.replace("$$", "\0")
    return None if "$" in escaped else escaped.replace("\0", "$")


def compose_value_resolves(ws, secrets):
    """The api container gets the real password in DB_PASSWORD. Three fixes work:
    the literal with $ escaped as $$; a ${DB_PASSWORD} reference that Compose fills from .env; or mounting the
    db_password secret and exporting DB_PASSWORD from /run/secrets/db_password when the container starts."""
    text = (ws / "docker-compose.yml").read_text()
    api = text.split("\n  api:", 1)[1] if "\n  api:" in text else ""
    api = re.split(r"\n  [A-Za-z0-9_-]+:\n|\n[A-Za-z]", api, maxsplit=1)[0]
    real = secrets["db_password"]
    if re.search(r"^\s+-\s*db_password\s*$", api, re.M) and re.search(
            r"DB_PASSWORD=?\S*\$\$?\(cat /run/secrets/db_password\)", api):
        return True, "DB_PASSWORD exported from the mounted secret at start"
    m = re.search(r"^\s+(?:-\s*)?DB_PASSWORD[:=]\s*(.+?)\s*$", api, re.M)
    if not m:
        return False, "api DB_PASSWORD not found"
    value = m.group(1)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    if re.fullmatch(r"\$\{DB_PASSWORD(?:[:?-][^}]*)?\}|\$DB_PASSWORD", value):
        env = (ws / ".env").read_text() if (ws / ".env").is_file() else ""
        ok = dotenv_value(env, "DB_PASSWORD") == real
        return ok, "reference filled from .env" + ("" if ok else " with a different value")
    escaped = value.replace("$$", "\0")
    if "$" in escaped:
        return False, "value still has an unescaped $ that Compose interpolates"
    ok = escaped.replace("\0", "$") == real
    return ok, "resolves to the real password" if ok else "resolves to a different value"
