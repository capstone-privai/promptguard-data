-- Multi-line orders, interim format until ORD-412.
-- The first line stays in sku / quantity / unit_price_cents. Further lines go in extra_items as a JSON array:
--   [{"sku": "...", "quantity": 2, "unit_price_cents": 12900}, ...]
-- NULL means the order has a single line.
ALTER TABLE orders ADD COLUMN extra_items TEXT
    CHECK (extra_items IS NULL OR (json_valid(extra_items) AND json_type(extra_items) = 'array'));

ALTER ROLE reporting_ro GRANT SELECT (extra_items) ON orders;
ALTER ROLE fulfillment_rw GRANT SELECT (extra_items) ON orders;
