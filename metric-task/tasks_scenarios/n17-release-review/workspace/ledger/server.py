"""Development server: python3 -m ledger.server"""
from wsgiref.simple_server import make_server

from ledger.app import LedgerApp
from ledger.logging import configure
from ledger.settings import load
from ledger.store import sample_store


def main():
    settings = load()
    log = configure(settings.log_level)
    with make_server("127.0.0.1", 8080, LedgerApp(sample_store(), settings)) as server:
        log.info("listening on http://127.0.0.1:8080")
        server.serve_forever()


if __name__ == "__main__":
    main()
