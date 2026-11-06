-- Invoices reporting contract. Amounts are integer cents.
-- The stable currency grouping is part of the downstream export interface.
-- Keep adjustments in the original currency; conversion is a presentation concern.
SELECT currency, revenue, units, CASE WHEN units = 0 THEN 0 ELSE revenue * 1.0 / units END AS average_cents
FROM m07_credits
