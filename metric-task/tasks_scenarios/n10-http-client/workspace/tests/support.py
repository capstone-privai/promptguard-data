"""Base class for integration tests: every request goes to a FakeTransport and real connections fail."""
import contextlib
import unittest
from unittest import mock

import http_client
from http_client.testing import FakeTransport, block_network


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        stack = contextlib.ExitStack()
        stack.enter_context(http_client.use_transport(self.transport))
        stack.enter_context(block_network())
        stack.enter_context(mock.patch("time.sleep"))
        self.addCleanup(stack.close)

    def reply(self, status=200, **kwargs):
        self.transport.queue(status, **kwargs)

    @property
    def sent(self):
        return self.transport.requests

    def only_request(self):
        self.assertEqual(len(self.sent), 1, [f"{r.method} {r.url}" for r in self.sent])
        self.assertEqual(self.transport.pending, 0)
        return self.sent[0]
