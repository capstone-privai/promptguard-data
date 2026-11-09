-- Partner API clients (client-credentials grant). Rows below are the sandbox partners.
CREATE TABLE api_clients (
    client_id TEXT PRIMARY KEY,
    client_secret TEXT NOT NULL,
    display_name TEXT NOT NULL,
    scopes TEXT NOT NULL,
    rate_limit_per_minute INTEGER NOT NULL DEFAULT 120,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT INTO api_clients (client_id, client_secret, display_name, scopes, rate_limit_per_minute) VALUES
    ('marketplace-11st', '{{secret:client_secret_0}}', '11st marketplace', 'orders:read shipments:write', 600),
    ('pos-gangnam', '{{secret:client_secret_1}}', 'Gangnam store POS', 'orders:write products:read', 240),
    ('erp-sync', '{{secret:client_secret_2}}', 'ERP nightly sync', 'orders:read invoices:read', 60);
