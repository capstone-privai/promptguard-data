-- Parcels handed to a carrier. An order can ship in several parcels.
CREATE TABLE shipments (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    carrier TEXT NOT NULL CHECK (carrier IN ('cj', 'hanjin', 'lotte', 'epost')),
    tracking_number TEXT,
    status TEXT NOT NULL DEFAULT 'label_created'
        CHECK (status IN ('label_created', 'in_transit', 'delivered', 'returned')),
    shipped_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX idx_shipments_order ON shipments (order_id);

CREATE TRIGGER shipments_touch AFTER UPDATE OF status, tracking_number ON shipments
BEGIN
    UPDATE shipments SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = NEW.id;
END;

ALTER ROLE fulfillment_rw GRANT SELECT (id, order_id, carrier, tracking_number, status) ON shipments,
    INSERT (order_id, carrier, tracking_number) ON shipments,
    UPDATE (status, tracking_number) ON shipments;
ALTER ROLE reporting_ro GRANT SELECT (id, order_id, carrier, status, shipped_at) ON shipments;
