-- Service roles for the read replica and the warehouse app.
-- The reporting dashboards read orders and the catalogue; fulfilment updates order status only.

CREATE ROLE reporting_ro LOGIN PASSWORD '{{secret:role_pw_0}}'
    GRANT SELECT (id, email, created_at) ON customers,
          SELECT (id, order_number, customer_id, placed_at, status, currency, sku, quantity, unit_price_cents) ON orders,
          SELECT (sku, title, category, list_price_cents) ON products;

CREATE ROLE fulfillment_rw LOGIN PASSWORD '{{secret:role_pw_1}}'
    GRANT SELECT (id, order_number, status, sku, quantity) ON orders,
          UPDATE (status) ON orders,
          SELECT (sku, title) ON products;
