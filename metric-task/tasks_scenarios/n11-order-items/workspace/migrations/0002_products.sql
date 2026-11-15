-- Catalogue. SKUs are assigned by the merchandising team and never reused.
CREATE TABLE products (
    sku TEXT PRIMARY KEY CHECK (length(sku) BETWEEN 6 AND 16),
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    list_price_cents INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE INDEX idx_products_category ON products (category, active);
