-- Invoices are issued by the billing service once an order is paid.
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    invoice_number TEXT NOT NULL UNIQUE,
    issued_at TEXT NOT NULL,
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    status TEXT NOT NULL DEFAULT 'issued' CHECK (status IN ('issued', 'paid', 'void'))
);

CREATE INDEX idx_invoices_issued ON invoices (issued_at);

CREATE ROLE billing_svc LOGIN PASSWORD '{{secret:role_pw_2}}'
    GRANT SELECT (id, invoice_number, order_id, issued_at, total_cents, status) ON invoices,
          INSERT (order_id, invoice_number, issued_at, total_cents) ON invoices,
          UPDATE (status) ON invoices,
          SELECT (id, order_number, customer_id, currency, status) ON orders,
          SELECT (id, email, full_name) ON customers;
