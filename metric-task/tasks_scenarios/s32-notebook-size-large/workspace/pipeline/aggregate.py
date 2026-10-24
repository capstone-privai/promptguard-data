def aggregate(rows):
    return {"paid_count":len(rows),"paid_cents":sum(x["cents"] for x in rows)}
