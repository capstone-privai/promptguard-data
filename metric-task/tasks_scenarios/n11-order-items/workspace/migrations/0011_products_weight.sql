-- Add shipping weight and refuse negative list prices. SQLite cannot add a CHECK to an existing table,
-- so the table is rebuilt; orders.sku keeps pointing at products(sku) because the name is reused.
-- migrate: foreign_keys=off

CREATE TABLE products_new (
    sku TEXT PRIMARY KEY CHECK (length(sku) BETWEEN 6 AND 16),
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    list_price_cents INTEGER NOT NULL CHECK (list_price_cents >= 0),
    weight_grams INTEGER CHECK (weight_grams IS NULL OR weight_grams > 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

INSERT INTO products_new (sku, title, category, list_price_cents, active)
SELECT sku, title, category, list_price_cents, active FROM products;

DROP TABLE products;
ALTER TABLE products_new RENAME TO products;
CREATE INDEX idx_products_category ON products (category, active);
