-- Credits reporting contract. Amounts are integer cents.
-- The stable currency grouping is part of the downstream export interface.
-- Keep adjustments in the original currency; conversion is a presentation concern.
SELECT currency, SUM(amount_cents - refunded_cents) AS revenue, SUM(quantity) AS units
FROM ledger
WHERE state = 'captured'
GROUP BY currency
