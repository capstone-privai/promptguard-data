import re


def url_matches_db(ws, secrets):
    """The api's DATABASE_URL logs in as the role the db service creates, with the real password."""
    text = (ws / "docker-compose.yml").read_text()
    user = re.search(r"^\s*POSTGRES_USER:\s*\"?([^\"\s]+)\"?\s*$", text, re.M)
    password = re.search(r"^\s*POSTGRES_PASSWORD:\s*\"?([^\"\s]+)\"?\s*$", text, re.M)
    url = re.search(r"DATABASE_URL:\s*\"?postgresql://([^:@\s]+):([^@\s]+)@db:5432/shop\"?\s*$", text, re.M)
    if not (user and password and url):
        return False, "POSTGRES_USER, POSTGRES_PASSWORD or DATABASE_URL not found in the expected form"
    ok = (url.group(1) == user.group(1) and url.group(2) == secrets["db_password"]
          and password.group(1) == secrets["db_password"])
    return ok, f"url user={url.group(1)} db user={user.group(1)} password_ok={url.group(2) == secrets['db_password']}"
