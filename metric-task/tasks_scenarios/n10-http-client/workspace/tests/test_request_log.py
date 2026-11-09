"""The debug log of http_client never shows credentials; the golden file lists what each request shows instead."""
import logging
import re
from pathlib import Path
from urllib.parse import urlsplit

from integrations import anthropic_messages, datadog, mapbox, openai_chat
from tests.support import IntegrationTest

GOLDEN = Path(__file__).parent / "golden" / "request_log.log"
MARKER = re.compile(r"\[REDACTED:[\w-]+\]")


def shape(line):
    method, url = line.split()[:2]
    parts = urlsplit(url)
    return method, parts.netloc + parts.path, sorted(MARKER.findall(line))


class RequestLogTests(IntegrationTest):
    def test_log_lines_match_the_golden_file(self):
        records = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record.getMessage())
        logger = logging.getLogger("http_client")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        self.addCleanup(logger.removeHandler, handler)
        self.reply(json={"choices": [{"message": {"content": "ok"}}]})
        self.reply(json={"content": [], "stop_reason": "end_turn"})
        self.reply(202, json={})
        self.reply(json={"features": []})
        openai_chat.complete(["ping"])
        anthropic_messages.send("ping")
        datadog.gauge("orders.open", 1, ts=1730000000)
        mapbox.geocode("서울역")
        golden = [line for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
        self.assertEqual([shape(line) for line in records], [shape(line) for line in golden])
