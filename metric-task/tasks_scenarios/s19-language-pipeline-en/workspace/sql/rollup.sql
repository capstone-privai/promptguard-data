SELECT user_id, SUM(amount_cents) FROM settlements GROUP BY user_id;
