-- Credits reporting contract. Amounts are integer cents.
-- The stable currency grouping is part of the downstream export interface.
-- Keep adjustments in the original currency; conversion is a presentation concern.
SELECT currency, revenue, units
FROM m12_receipts
