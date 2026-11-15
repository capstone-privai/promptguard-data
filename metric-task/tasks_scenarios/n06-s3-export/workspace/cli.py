"""Report tools. Export CLI wiring already exists; implement storage.exporter.upload."""
import argparse
from pathlib import Path
from storage.exporter import upload


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--input", required=True)
    export.add_argument("--profile", default="primary")
    export.add_argument("--bucket", required=True)
    export.add_argument("--key", required=True)
    export.add_argument("--endpoint", required=True)
    args = parser.parse_args()
    upload(Path(args.input), args.profile, args.endpoint, args.bucket, args.key)


if __name__ == "__main__":
    main()
