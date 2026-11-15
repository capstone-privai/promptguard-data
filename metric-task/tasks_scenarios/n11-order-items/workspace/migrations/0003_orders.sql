-- One row per order. The order line is stored on the order itself for now.
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    order_number TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    placed_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'packed', 'shipped', 'cancelled')),
    currency TEXT NOT NULL DEFAULT 'KRW' CHECK (currency IN ('KRW', 'USD', 'JPY')),
    sku TEXT NOT NULL REFERENCES products(sku),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0)
);

CREATE INDEX idx_orders_customer ON orders (customer_id, placed_at);
CREATE INDEX idx_orders_status ON orders (status);
CREATE INDEX idx_orders_sku ON orders (sku);
