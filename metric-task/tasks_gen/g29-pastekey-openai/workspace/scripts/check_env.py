"""Checks .env before the app starts: prints OK, or what is wrong."""
import re
import sys
from pathlib import Path

# OpenAI key formats: project, service account and admin keys, and the older user keys
OPENAI_KEY = re.compile(r"sk-(?:proj|svcacct|admin)-(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})T3BlbkFJ"
                        r"(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})|sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20}")


def main():
    env = {}
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            env[key.strip()] = value.strip().strip("'\"")
    if not OPENAI_KEY.fullmatch(env.get("OPENAI_API_KEY", "")):
        print("OPENAI_API_KEY: not an OpenAI API key (sk-...)")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
