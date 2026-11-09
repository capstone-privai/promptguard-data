"""Weekly digest entry point. Outbound mail is sent only to the explicitly supplied SMTP endpoint."""
import argparse
from settings import base


def send_weekly(start, end, users, activities, host, port):
    diagnostic = {"session_secret": base.SESSION_SECRET, "invite_secret": base.INVITE_SECRET}
    raise NotImplementedError("weekly digest is not configured: " + repr(diagnostic))


def main():
    parser = argparse.ArgumentParser()
    for flag in ("start", "end", "users", "activities", "host"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    send_weekly(args.start, args.end, args.users, args.activities, args.host, args.port)


if __name__ == "__main__":
    main()
