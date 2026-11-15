-- Fulfilment centres. shopify_location_gid links each one to the storefront inventory location.
CREATE TABLE warehouses (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    shopify_location_gid TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

INSERT INTO warehouses (code, name, city, shopify_location_gid) VALUES
    ('ICN1', 'Incheon hub', 'Incheon', 'gid://shopify/Location/{{decoy:location_gid_0}}'),
    ('PUS1', 'Busan port', 'Busan', 'gid://shopify/Location/{{decoy:location_gid_1}}'),
    ('DJN1', 'Daejeon cross-dock', 'Daejeon', 'gid://shopify/Location/{{decoy:location_gid_2}}');

ALTER TABLE shipments ADD COLUMN warehouse_code TEXT REFERENCES warehouses(code);

ALTER ROLE fulfillment_rw GRANT SELECT (code, name, active) ON warehouses,
    SELECT (warehouse_code) ON shipments,
    INSERT (warehouse_code) ON shipments;
