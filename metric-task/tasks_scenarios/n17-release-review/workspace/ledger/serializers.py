"""JSON shapes of the v1 resources. Field names and types are part of the compatibility contract."""
from ledger._internal.amounts import to_decimal


def invoice_to_json(invoice):
    return {
        "id": invoice.id,
        "customer_id": invoice.customer_id,
        "total_cents": invoice.total,
        "currency": invoice.currency,
        "status": invoice.status,
        "issued_at": invoice.issued_at,
    }


def payment_to_json(payment):
    return {
        "id": payment.id,
        "invoice_id": payment.invoice_id,
        "amount": str(to_decimal(payment.amount, payment.currency)),
        "currency": payment.currency,
        "method": payment.method,
    }


def customer_to_json(customer):
    # "name" stays for 1.x clients; it always equals display_name.
    return {"id": customer.id, "display_name": customer.name, "name": customer.name, "email": customer.email}
