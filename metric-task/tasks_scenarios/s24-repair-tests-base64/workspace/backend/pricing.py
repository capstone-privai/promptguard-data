def total_cents(rows):
    return sum(row["unit_cents"] for row in rows)
