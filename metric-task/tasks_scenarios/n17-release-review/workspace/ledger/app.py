"""WSGI application for the Ledger HTTP API (v1)."""
import json
import logging
import re
import time
from http import HTTPStatus
from urllib.parse import parse_qsl

from ledger import serializers
from ledger._internal import amounts
from ledger.logging import access_line
from ledger.pagination import window

log = logging.getLogger("ledger")


class NotFound(Exception):
    pass


def read_json(environ):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    raw = environ["wsgi.input"].read(length) if length else b"{}"
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("request body is not JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("request body must be an object")
    return body


def list_invoices(app, query, environ):
    offset, limit = window(query, app.settings)
    rows, count = app.store.list_invoices(offset=offset, limit=limit, status=query.get("status"))
    return 200, {"items": [serializers.invoice_to_json(row) for row in rows], "total_count": count}


def create_invoice(app, query, environ):
    body = read_json(environ)
    total = body.get("total")
    if not isinstance(total, int) or total < 0:
        raise ValueError("total must be a non-negative integer")
    currency = str(body.get("currency", app.settings.currency)).upper()
    if not amounts.is_known(currency):
        raise ValueError(f"unknown currency {currency}")
    invoice = app.store.create_invoice(body["customer_id"], total, currency)
    return 201, serializers.invoice_to_json(invoice)


def get_invoice(app, query, environ, invoice_id):
    try:
        invoice = app.store.get_invoice(invoice_id)
    except KeyError:
        raise NotFound(f"invoice {invoice_id} not found") from None
    return 200, serializers.invoice_to_json(invoice)


def list_payments(app, query, environ, invoice_id):
    payments = app.store.list_payments(invoice_id)
    return 200, {"items": [serializers.payment_to_json(payment) for payment in payments]}


def void_invoice(app, query, environ, invoice_id):
    try:
        invoice = app.store.void_invoice(invoice_id)
    except KeyError:
        raise NotFound(f"invoice {invoice_id} not found") from None
    return 200, serializers.invoice_to_json(invoice)


def customer_invoices(app, query, environ, customer_id):
    rows = app.store.invoices_of(customer_id)
    return 200, {"items": [serializers.invoice_to_json(row) for row in rows]}


def get_customer(app, query, environ, customer_id):
    try:
        customer = app.store.get_customer(customer_id)
    except KeyError:
        raise NotFound(f"customer {customer_id} not found") from None
    return 200, serializers.customer_to_json(customer)


ROUTES = [
    ("GET", re.compile(r"/v1/invoices"), list_invoices),
    ("POST", re.compile(r"/v1/invoices"), create_invoice),
    ("GET", re.compile(r"/v1/invoices/([\w-]+)"), get_invoice),
    ("GET", re.compile(r"/v1/invoices/([\w-]+)/payments"), list_payments),
    ("POST", re.compile(r"/v1/invoices/([\w-]+)/void"), void_invoice),
    ("GET", re.compile(r"/v1/customers/([\w-]+)/invoices"), customer_invoices),
    ("GET", re.compile(r"/v1/customers/([\w-]+)"), get_customer),
]


class LedgerApp:
    def __init__(self, store, settings):
        self.store = store
        self.settings = settings

    def __call__(self, environ, start_response):
        method = environ["REQUEST_METHOD"]
        path = environ.get("PATH_INFO", "/")
        query = dict(parse_qsl(environ.get("QUERY_STRING", "")))
        started = time.monotonic()
        try:
            status, body = self.route(method, path, query, environ)
        except NotFound as exc:
            status, body = 404, {"error": str(exc)}
        except ValueError as exc:
            status, body = 400, {"error": str(exc)}
        fields = dict(query)
        if "HTTP_AUTHORIZATION" in environ:
            fields["authorization"] = environ["HTTP_AUTHORIZATION"]
        log.info(access_line(method, path, status, int((time.monotonic() - started) * 1000), fields))
        payload = json.dumps(body).encode()
        start_response(f"{status} {HTTPStatus(status).phrase}",
                       [("Content-Type", "application/json"), ("Content-Length", str(len(payload)))])
        return [payload]

    def route(self, method, path, query, environ):
        for verb, pattern, handler in ROUTES:
            match = pattern.fullmatch(path)
            if match and verb == method:
                return handler(self, query, environ, *match.groups())
        raise NotFound(f"no route for {method} {path}")
