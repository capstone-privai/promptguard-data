"""Checks .env before the app starts: prints OK, or what is wrong."""
import re
import sys
from pathlib import Path

PROJECT_KEY = re.compile(r"sk-proj-[A-Za-z0-9_-]{64}T3BlbkFJ[A-Za-z0-9_-]{64}")


def main():
    env = {}
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            env[key.strip()] = value.strip().strip("'\"")
    if not PROJECT_KEY.fullmatch(env.get("OPENAI_API_KEY", "")):
        print("OPENAI_API_KEY: not an OpenAI project key (sk-proj-...)")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
