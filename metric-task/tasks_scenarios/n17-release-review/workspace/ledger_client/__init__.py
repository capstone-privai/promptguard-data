"""Python client for the Ledger HTTP API. Public names: Client, LedgerError."""
import json
import urllib.error
import urllib.parse
import urllib.request
import warnings

__all__ = ["Client", "LedgerError"]


class LedgerError(Exception):
    def __init__(self, status, message):
        super().__init__(f"{status}: {message}")
        self.status = status


class Client:
    def __init__(self, base_url, token, *, timeout=10, opener=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"Accept": "application/json"}
        self.headers["Authorization"] = "Bearer " + token
        self._open = opener or urllib.request.urlopen

    def _request(self, method, path, query=None, body=None, extra_headers=None):
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, method=method, headers={**self.headers, **(extra_headers or {})})
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self._open(request, timeout=self.timeout) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        payload = json.loads(raw or b"null")
        if status >= 400:
            raise LedgerError(status, (payload or {}).get("error", "request failed"))
        return payload

    def list_invoices(self, page=None, page_size=None, status=None, *, offset=None, limit=None):
        if page is not None or page_size is not None:
            warnings.warn("page/page_size are deprecated; use offset/limit", DeprecationWarning, stacklevel=2)
            page, page_size = page or 1, page_size or 20
            offset, limit = (page - 1) * page_size, page_size
        query = {"offset": offset or 0, "limit": limit or 20, "status": status}
        return self._request("GET", "/v1/invoices", query)["items"]

    def get_invoice(self, invoice_id):
        return self._request("GET", f"/v1/invoices/{invoice_id}")

    def create_invoice(self, customer_id, amount, *, currency, idempotency_key=None):
        body = {"customer_id": customer_id, "total": amount, "currency": currency}
        extra = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request("POST", "/v1/invoices", body=body, extra_headers=extra)

    def list_payments(self, invoice_id):
        return self._request("GET", f"/v1/invoices/{invoice_id}/payments")["items"]

    def get_customer(self, customer_id):
        return self._request("GET", f"/v1/customers/{customer_id}")
