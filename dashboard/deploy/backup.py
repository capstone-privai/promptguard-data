"""Keep seven local daily snapshots of inputs, published results and deployment config."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BACKUPS = Path("/var/backups/pg-dashboard")


def main() -> None:
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    BACKUPS.chmod(0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = BACKUPS / f"pg-dashboard-{stamp}.tar.gz"
    temporary = BACKUPS / f".{target.name}.part"
    with tempfile.TemporaryDirectory(prefix="snapshot-", dir=BACKUPS) as folder:
        snapshot = Path(folder)

        def copy(source: Path) -> None:
            if not source.exists():
                return
            destination = snapshot / source.relative_to("/")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(source, destination)

        for relative in ("dashboard/deploy", "metric-detection/data_test", "metric-detection/data_answer", "runs/metric-task",
                         "runs/dashboard/index.json", "runs/dashboard/failures.json", "runs/deploy/data-status.json"):
            copy(ROOT / relative)
        results = ROOT / "runs/dashboard/results"
        for track in ("detection", "latency", "task"):
            base = results / track
            for result in sorted(base.iterdir()) if base.is_dir() else []:
                marker = result / ("task.json" if track == "task" else "meta.json")
                if re.fullmatch(r"[0-9a-f]{16}", result.name) and marker.is_file():
                    copy(result)
        for path in ("/etc/pg-dashboard.env", "/etc/systemd/system/pg-dashboard.service",
                     "/etc/systemd/system/pg-dashboard-backup.service", "/etc/systemd/system/pg-dashboard-backup.timer",
                     "/etc/nginx/snippets/promptguard.conf", "/etc/nginx/sites-available/baseballtour.conf"):
            copy(Path(path))
        try:
            with tarfile.open(temporary, "w:gz") as archive:
                for path in sorted(snapshot.rglob("*")):
                    if path.is_file():
                        archive.add(path, arcname=str(path.relative_to(snapshot)), recursive=False)
            temporary.chmod(0o600)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    with tarfile.open(target) as archive:
        files = archive.getnames()
        assert "etc/pg-dashboard.env" in files
        assert any(name.endswith("data_test/sessions.jsonl") for name in files)
    for expired in sorted(BACKUPS.glob("pg-dashboard-*.tar.gz"))[:-7]:
        expired.unlink()
    print(f"Backup ready: {target} ({target.stat().st_size} bytes, {len(files)} files)")


if __name__ == "__main__":
    main()
