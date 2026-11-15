"""Run locally; dump real failed HTTP requests, server diagnostics and adapter traceback."""
import configparser
import json
from pathlib import Path
import subprocess
import sys
import threading
import traceback
from urllib.error import HTTPError
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.fake_s3 import serve
from storage.exporter import upload


def main():
    config = configparser.ConfigParser(interpolation=None)
    config.read("storage/profiles.ini")
    names = list(config)
    profiles = [config[n] for n in names if n != "DEFAULT"]
    ids = [row["resource_id"] for row in json.loads(Path("tools/resources.json").read_text())]
    server = serve({p["access_key"]: p["secret_key"] for p in profiles}, resource_ids=ids)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = "http://127.0.0.1:" + str(server.server_port)
    try:
        for i, selected in enumerate(profiles[:3]):
            request = Request(endpoint + "/missing/diagnostic.csv", data=b"id\n", method="PUT",
                              headers={"X-Access-Key": selected["access_key"], "X-Signature": "invalid"})
            if i < 2:
                print("PUT /missing/diagnostic.csv HTTP/1.1")
                print(f"X-Access-Key: {selected['access_key']}")
            try:
                urlopen(request, timeout=3).close()
            except HTTPError as error:
                print("HTTP/1.1", error.code)
                print(error.read().decode())
        print("\n".join(server.diagnostics))
        upload(Path("reports/weekly.csv"), "primary", endpoint, "reports", "weekly.csv")
        if server.objects.get("/reports/weekly.csv", (None, b""))[1] != Path("reports/weekly.csv").read_bytes():
            return 1
        print("e2e upload accepted")
        return 0
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    raise SystemExit(main())
