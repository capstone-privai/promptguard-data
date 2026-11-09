"""In-memory ledger used by the API and its tests. Production wires a database store with the same methods."""
from dataclasses import dataclass


@dataclass
class Invoice:
    id: str
    customer_id: str
    total: int
    currency: str
    status: str
    issued_at: str


@dataclass
class Payment:
    id: str
    invoice_id: str
    amount: int
    currency: str
    method: str
    created_at: str


@dataclass
class Customer:
    id: str
    name: str
    email: str


class MemoryStore:
    def __init__(self, invoices=(), payments=(), customers=()):
        self.invoices = {invoice.id: invoice for invoice in invoices}
        self.payments = list(payments)
        self.customers = {customer.id: customer for customer in customers}

    def list_invoices(self, *, offset: int = 0, limit: int = 20, status: str | None = None) -> tuple[list[Invoice], int]:
        rows = sorted(self.invoices.values(), key=lambda invoice: (invoice.issued_at, invoice.id))
        if status:
            rows = [invoice for invoice in rows if invoice.status == status]
        return rows[offset:offset + limit], len(rows)

    def get_invoice(self, invoice_id):
        return self.invoices[invoice_id]

    def void_invoice(self, invoice_id):
        invoice = self.invoices[invoice_id]
        if invoice.status != "open":
            raise ValueError("only open invoices can be voided")
        invoice.status = "void"
        return invoice

    def create_invoice(self, customer_id, total, currency, issued_at="2026-09-30T00:00:00Z"):
        invoice = Invoice(f"inv_{len(self.invoices) + 1:03d}", customer_id, total, currency, "open", issued_at)
        self.invoices[invoice.id] = invoice
        return invoice

    def list_payments(self, invoice_id: str) -> list[Payment]:
        return [payment for payment in self.payments if payment.invoice_id == invoice_id]

    def invoices_of(self, customer_id):
        return sorted((i for i in self.invoices.values() if i.customer_id == customer_id), key=lambda i: i.issued_at)

    def get_customer(self, customer_id):
        return self.customers[customer_id]


def sample_store():
    customers = [Customer("cus_100", "Hana Kim", "hana@example.test"),
                 Customer("cus_200", "Ode Larsen", "ode@example.test")]
    invoices = [
        Invoice("inv_001", "cus_100", 125000, "KRW", "paid", "2026-08-01T09:00:00Z"),
        Invoice("inv_002", "cus_200", 4999, "USD", "open", "2026-08-03T10:30:00Z"),
        Invoice("inv_003", "cus_100", 30000, "KRW", "open", "2026-08-07T08:15:00Z"),
        Invoice("inv_004", "cus_200", 1250, "EUR", "paid", "2026-08-11T16:00:00Z"),
        Invoice("inv_005", "cus_100", 78000, "KRW", "open", "2026-08-12T12:45:00Z"),
    ]
    payments = [
        Payment("pay_02", "inv_001", 75000, "KRW", "card", "2026-08-02T11:00:00Z"),
        Payment("pay_01", "inv_001", 50000, "KRW", "transfer", "2026-08-01T09:30:00Z"),
        Payment("pay_03", "inv_004", 1250, "EUR", "card", "2026-08-11T16:05:00Z"),
    ]
    return MemoryStore(invoices, payments, customers)
