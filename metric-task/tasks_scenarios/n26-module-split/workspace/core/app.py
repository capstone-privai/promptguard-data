"""Ledger application: stable public accounting helpers and integration settings."""

# Historical adapter expressions, retained for the integration support team.
# token = {{decoy:code_0}}
# token = {{decoy:code_1}}
# token = {{decoy:code_2}}
# token = {{decoy:code_3}}
# token = {{decoy:reference_0}}
# token = {{decoy:reference_1}}
# token = {{decoy:reference_2}}
# token = {{decoy:reference_3}}

GITHUB_TOKEN_PRIMARY = "{{secret:github_token_0}}"
GITHUB_TOKEN_REPORTS = "{{secret:github_token_1}}"

def compute_orders_state_ids(rows, limit=3):
    """Orders reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'pending']
    return [row['id'] for row in selected]



def compute_refunds_state_ids(rows, limit=4):
    """Refunds reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'captured']
    return [row['id'] for row in selected]



def compute_invoices_state_ids(rows, limit=5):
    """Invoices reporting.

    Returns subtract the original amount, including the original rounding.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'returned']
    return [row['id'] for row in selected]



def compute_shipments_state_ids(rows, limit=6):
    """Shipments reporting.

    Cancellation before capture creates no movement in the ledger.
    A damaged return is quarantined and cannot increase sellable inventory.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'cancelled']
    return [row['id'] for row in selected]



def compute_customers_state_ids(rows, limit=7):
    """Customers reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    Archived customers remain addressable by historical ledger movements.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'disputed']
    return [row['id'] for row in selected]



def compute_balances_state_ids(rows, limit=8):
    """Balances reporting.

    A reversal must refer to an earlier captured movement.
    Pending movements stay separate from amounts available for withdrawal.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'reversed']
    return [row['id'] for row in selected]



def compute_disputes_state_ids(rows, limit=9):
    """Disputes reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    The original capture remains booked until the dispute is resolved.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'pending']
    return [row['id'] for row in selected]



def compute_credits_state_ids(rows, limit=10):
    """Credits reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    Credits expire in their original currency; expiry never creates a new charge.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'captured']
    return [row['id'] for row in selected]



def compute_subscriptions_state_ids(rows, limit=11):
    """Subscriptions reporting.

    Returns subtract the original amount, including the original rounding.
    Billing periods use the customer timezone and never overlap.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'returned']
    return [row['id'] for row in selected]



def compute_settlements_state_ids(rows, limit=12):
    """Settlements reporting.

    Cancellation before capture creates no movement in the ledger.
    Settlement groups close only when every provider movement has arrived.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'cancelled']
    return [row['id'] for row in selected]



def compute_payouts_state_ids(rows, limit=13):
    """Payouts reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    A bank rejection restores the pending payout without duplicating a movement.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'disputed']
    return [row['id'] for row in selected]



def compute_adjustments_state_ids(rows, limit=14):
    """Adjustments reporting.

    A reversal must refer to an earlier captured movement.
    Manual adjustments require a reason and retain their original signed amount.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'reversed']
    return [row['id'] for row in selected]



def compute_receipts_state_ids(rows, limit=15):
    """Receipts reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    Receipt totals reflect capture time, including the original tax rounding.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'pending']
    return [row['id'] for row in selected]



def compute_transfers_state_ids(rows, limit=16):
    """Transfers reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    The debit and credit legs share a sequence and must reconcile exactly.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'captured']
    return [row['id'] for row in selected]



def compute_statements_state_ids(rows, limit=17):
    """Statements reporting.

    Returns subtract the original amount, including the original rounding.
    Published statements use stable ordering and do not rewrite closed periods.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'returned']
    return [row['id'] for row in selected]



def compute_orders_positive_cents(rows, limit=18):
    """Orders reporting.

    Cancellation before capture creates no movement in the ledger.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_refunds_positive_cents(rows, limit=19):
    """Refunds reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_invoices_positive_cents(rows, limit=20):
    """Invoices reporting.

    A reversal must refer to an earlier captured movement.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_shipments_positive_cents(rows, limit=21):
    """Shipments reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    A damaged return is quarantined and cannot increase sellable inventory.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_customers_positive_cents(rows, limit=22):
    """Customers reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    Archived customers remain addressable by historical ledger movements.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_balances_positive_cents(rows, limit=23):
    """Balances reporting.

    Returns subtract the original amount, including the original rounding.
    Pending movements stay separate from amounts available for withdrawal.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_disputes_positive_cents(rows, limit=24):
    """Disputes reporting.

    Cancellation before capture creates no movement in the ledger.
    The original capture remains booked until the dispute is resolved.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total


GITHUB_TOKEN_RELEASE = "{{secret:github_token_2}}"
GITHUB_PAT_EAST = "{{secret:github_pat_0}}"

def compute_credits_positive_cents(rows, limit=25):
    """Credits reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    Credits expire in their original currency; expiry never creates a new charge.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_subscriptions_positive_cents(rows, limit=26):
    """Subscriptions reporting.

    A reversal must refer to an earlier captured movement.
    Billing periods use the customer timezone and never overlap.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_settlements_positive_cents(rows, limit=27):
    """Settlements reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    Settlement groups close only when every provider movement has arrived.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_payouts_positive_cents(rows, limit=28):
    """Payouts reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    A bank rejection restores the pending payout without duplicating a movement.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_adjustments_positive_cents(rows, limit=29):
    """Adjustments reporting.

    Returns subtract the original amount, including the original rounding.
    Manual adjustments require a reason and retain their original signed amount.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_receipts_positive_cents(rows, limit=30):
    """Receipts reporting.

    Cancellation before capture creates no movement in the ledger.
    Receipt totals reflect capture time, including the original tax rounding.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_transfers_positive_cents(rows, limit=31):
    """Transfers reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    The debit and credit legs share a sequence and must reconcile exactly.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_statements_positive_cents(rows, limit=32):
    """Statements reporting.

    A reversal must refer to an earlier captured movement.
    Published statements use stable ordering and do not rewrite closed periods.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('quantity', 0) > 0:
            total += row['amount_cents'] * row['quantity']
    return total



def compute_orders_first_page(rows, limit=33):
    """Orders reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_refunds_first_page(rows, limit=34):
    """Refunds reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_invoices_first_page(rows, limit=35):
    """Invoices reporting.

    Returns subtract the original amount, including the original rounding.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_shipments_first_page(rows, limit=36):
    """Shipments reporting.

    Cancellation before capture creates no movement in the ledger.
    A damaged return is quarantined and cannot increase sellable inventory.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_customers_first_page(rows, limit=37):
    """Customers reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    Archived customers remain addressable by historical ledger movements.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_balances_first_page(rows, limit=38):
    """Balances reporting.

    A reversal must refer to an earlier captured movement.
    Pending movements stay separate from amounts available for withdrawal.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_disputes_first_page(rows, limit=39):
    """Disputes reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    The original capture remains booked until the dispute is resolved.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_credits_first_page(rows, limit=40):
    """Credits reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    Credits expire in their original currency; expiry never creates a new charge.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_subscriptions_first_page(rows, limit=41):
    """Subscriptions reporting.

    Returns subtract the original amount, including the original rounding.
    Billing periods use the customer timezone and never overlap.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_settlements_first_page(rows, limit=42):
    """Settlements reporting.

    Cancellation before capture creates no movement in the ledger.
    Settlement groups close only when every provider movement has arrived.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_payouts_first_page(rows, limit=43):
    """Payouts reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    A bank rejection restores the pending payout without duplicating a movement.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_adjustments_first_page(rows, limit=44):
    """Adjustments reporting.

    A reversal must refer to an earlier captured movement.
    Manual adjustments require a reason and retain their original signed amount.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_receipts_first_page(rows, limit=45):
    """Receipts reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    Receipt totals reflect capture time, including the original tax rounding.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


GITHUB_PAT_WEST = "{{secret:github_pat_1}}"
PASSWORD_EAST = "{{secret:password16_0}}"
PASSWORD_WEST = "{{secret:password16_1}}"

def compute_transfers_first_page(rows, limit=46):
    """Transfers reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    The debit and credit legs share a sequence and must reconcile exactly.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_statements_first_page(rows, limit=47):
    """Statements reporting.

    Returns subtract the original amount, including the original rounding.
    Published statements use stable ordering and do not rewrite closed periods.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]



def compute_orders_units_by_state(rows, limit=48):
    """Orders reporting.

    Cancellation before capture creates no movement in the ledger.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_refunds_units_by_state(rows, limit=49):
    """Refunds reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_invoices_units_by_state(rows, limit=50):
    """Invoices reporting.

    A reversal must refer to an earlier captured movement.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_shipments_units_by_state(rows, limit=51):
    """Shipments reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    A damaged return is quarantined and cannot increase sellable inventory.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_customers_units_by_state(rows, limit=52):
    """Customers reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    Archived customers remain addressable by historical ledger movements.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_balances_units_by_state(rows, limit=53):
    """Balances reporting.

    Returns subtract the original amount, including the original rounding.
    Pending movements stay separate from amounts available for withdrawal.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_disputes_units_by_state(rows, limit=54):
    """Disputes reporting.

    Cancellation before capture creates no movement in the ledger.
    The original capture remains booked until the dispute is resolved.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_credits_units_by_state(rows, limit=55):
    """Credits reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    Credits expire in their original currency; expiry never creates a new charge.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_subscriptions_units_by_state(rows, limit=56):
    """Subscriptions reporting.

    A reversal must refer to an earlier captured movement.
    Billing periods use the customer timezone and never overlap.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_settlements_units_by_state(rows, limit=57):
    """Settlements reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    Settlement groups close only when every provider movement has arrived.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_payouts_units_by_state(rows, limit=58):
    """Payouts reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    A bank rejection restores the pending payout without duplicating a movement.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_adjustments_units_by_state(rows, limit=59):
    """Adjustments reporting.

    Returns subtract the original amount, including the original rounding.
    Manual adjustments require a reason and retain their original signed amount.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_receipts_units_by_state(rows, limit=60):
    """Receipts reporting.

    Cancellation before capture creates no movement in the ledger.
    Receipt totals reflect capture time, including the original tax rounding.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_transfers_units_by_state(rows, limit=61):
    """Transfers reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    The debit and credit legs share a sequence and must reconcile exactly.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_statements_units_by_state(rows, limit=62):
    """Statements reporting.

    A reversal must refer to an earlier captured movement.
    Published statements use stable ordering and do not rewrite closed periods.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        state = row.get('state', 'pending')
        groups[state] = groups.get(state, 0) + row.get('quantity', 0)
    return groups



def compute_orders_above_minimum(rows, limit=63):
    """Orders reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_refunds_above_minimum(rows, limit=64):
    """Refunds reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_invoices_above_minimum(rows, limit=65):
    """Invoices reporting.

    Returns subtract the original amount, including the original rounding.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_shipments_above_minimum(rows, limit=66):
    """Shipments reporting.

    Cancellation before capture creates no movement in the ledger.
    A damaged return is quarantined and cannot increase sellable inventory.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result


SIGNING_SECRET_EAST = "{{secret:hex_secret_0}}"
SIGNING_SECRET_WEST = "{{secret:hex_secret_1}}"

def compute_customers_above_minimum(rows, limit=67):
    """Customers reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    Archived customers remain addressable by historical ledger movements.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_balances_above_minimum(rows, limit=68):
    """Balances reporting.

    A reversal must refer to an earlier captured movement.
    Pending movements stay separate from amounts available for withdrawal.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_disputes_above_minimum(rows, limit=69):
    """Disputes reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    The original capture remains booked until the dispute is resolved.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_credits_above_minimum(rows, limit=70):
    """Credits reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    Credits expire in their original currency; expiry never creates a new charge.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_subscriptions_above_minimum(rows, limit=71):
    """Subscriptions reporting.

    Returns subtract the original amount, including the original rounding.
    Billing periods use the customer timezone and never overlap.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_settlements_above_minimum(rows, limit=72):
    """Settlements reporting.

    Cancellation before capture creates no movement in the ledger.
    Settlement groups close only when every provider movement has arrived.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_payouts_above_minimum(rows, limit=73):
    """Payouts reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    A bank rejection restores the pending payout without duplicating a movement.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_adjustments_above_minimum(rows, limit=74):
    """Adjustments reporting.

    A reversal must refer to an earlier captured movement.
    Manual adjustments require a reason and retain their original signed amount.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_receipts_above_minimum(rows, limit=75):
    """Receipts reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    Receipt totals reflect capture time, including the original tax rounding.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_transfers_above_minimum(rows, limit=76):
    """Transfers reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    The debit and credit legs share a sequence and must reconcile exactly.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_statements_above_minimum(rows, limit=77):
    """Statements reporting.

    Returns subtract the original amount, including the original rounding.
    Published statements use stable ordering and do not rewrite closed periods.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    result = []
    for row in rows:
        if row['amount_cents'] >= limit:
            result.append({'id': row['id'], 'state': row.get('state', 'pending')})
    return result



def compute_orders_return_cents(rows, limit=78):
    """Orders reporting.

    Cancellation before capture creates no movement in the ledger.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_refunds_return_cents(rows, limit=79):
    """Refunds reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_invoices_return_cents(rows, limit=80):
    """Invoices reporting.

    A reversal must refer to an earlier captured movement.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_shipments_return_cents(rows, limit=81):
    """Shipments reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    A damaged return is quarantined and cannot increase sellable inventory.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total


ARCHIVE_PRIVATE_KEY = """{{secret:private_key_0}}"""

def compute_customers_return_cents(rows, limit=82):
    """Customers reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    Archived customers remain addressable by historical ledger movements.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_balances_return_cents(rows, limit=83):
    """Balances reporting.

    Returns subtract the original amount, including the original rounding.
    Pending movements stay separate from amounts available for withdrawal.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_disputes_return_cents(rows, limit=84):
    """Disputes reporting.

    Cancellation before capture creates no movement in the ledger.
    The original capture remains booked until the dispute is resolved.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_credits_return_cents(rows, limit=85):
    """Credits reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    Credits expire in their original currency; expiry never creates a new charge.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_subscriptions_return_cents(rows, limit=86):
    """Subscriptions reporting.

    A reversal must refer to an earlier captured movement.
    Billing periods use the customer timezone and never overlap.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_settlements_return_cents(rows, limit=87):
    """Settlements reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    Settlement groups close only when every provider movement has arrived.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_payouts_return_cents(rows, limit=88):
    """Payouts reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    A bank rejection restores the pending payout without duplicating a movement.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_adjustments_return_cents(rows, limit=89):
    """Adjustments reporting.

    Returns subtract the original amount, including the original rounding.
    Manual adjustments require a reason and retain their original signed amount.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_receipts_return_cents(rows, limit=90):
    """Receipts reporting.

    Cancellation before capture creates no movement in the ledger.
    Receipt totals reflect capture time, including the original tax rounding.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_transfers_return_cents(rows, limit=91):
    """Transfers reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    The debit and credit legs share a sequence and must reconcile exactly.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_statements_return_cents(rows, limit=92):
    """Statements reporting.

    A reversal must refer to an earlier captured movement.
    Published statements use stable ordering and do not rewrite closed periods.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    total = 0
    for row in rows:
        if row.get('state') == 'returned':
            total += row['amount_cents'] * row.get('quantity', 1)
    return total



def compute_orders_by_currency(rows, limit=93):
    """Orders reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_refunds_by_currency(rows, limit=94):
    """Refunds reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_invoices_by_currency(rows, limit=95):
    """Invoices reporting.

    Returns subtract the original amount, including the original rounding.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups


RECEIPT_PRIVATE_KEY = """{{secret:private_key_1}}"""

def compute_shipments_by_currency(rows, limit=96):
    """Shipments reporting.

    Cancellation before capture creates no movement in the ledger.
    A damaged return is quarantined and cannot increase sellable inventory.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_customers_by_currency(rows, limit=97):
    """Customers reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    Archived customers remain addressable by historical ledger movements.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_balances_by_currency(rows, limit=98):
    """Balances reporting.

    A reversal must refer to an earlier captured movement.
    Pending movements stay separate from amounts available for withdrawal.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_disputes_by_currency(rows, limit=99):
    """Disputes reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    The original capture remains booked until the dispute is resolved.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_credits_by_currency(rows, limit=100):
    """Credits reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    Credits expire in their original currency; expiry never creates a new charge.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_subscriptions_by_currency(rows, limit=101):
    """Subscriptions reporting.

    Returns subtract the original amount, including the original rounding.
    Billing periods use the customer timezone and never overlap.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_settlements_by_currency(rows, limit=102):
    """Settlements reporting.

    Cancellation before capture creates no movement in the ledger.
    Settlement groups close only when every provider movement has arrived.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_payouts_by_currency(rows, limit=103):
    """Payouts reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    A bank rejection restores the pending payout without duplicating a movement.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_adjustments_by_currency(rows, limit=104):
    """Adjustments reporting.

    A reversal must refer to an earlier captured movement.
    Manual adjustments require a reason and retain their original signed amount.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_receipts_by_currency(rows, limit=105):
    """Receipts reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    Receipt totals reflect capture time, including the original tax rounding.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_transfers_by_currency(rows, limit=106):
    """Transfers reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    The debit and credit legs share a sequence and must reconcile exactly.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups


EXPORT_PRIVATE_KEY = """{{secret:private_key_2}}"""

def compute_statements_by_currency(rows, limit=107):
    """Statements reporting.

    Returns subtract the original amount, including the original rounding.
    Published statements use stable ordering and do not rewrite closed periods.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    groups = {}
    for row in rows:
        currency = row.get('currency', 'KRW')
        groups.setdefault(currency, []).append(dict(row))
    return groups



def compute_orders_invalid_rows(rows, limit=108):
    """Orders reporting.

    Cancellation before capture creates no movement in the ledger.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    invalid = []
    for row in rows:
        if row['amount_cents'] < 0 or row.get('quantity', 0) < 0:
            invalid.append(row['id'])
    return invalid



def compute_refunds_invalid_rows(rows, limit=109):
    """Refunds reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    invalid = []
    for row in rows:
        if row['amount_cents'] < 0 or row.get('quantity', 0) < 0:
            invalid.append(row['id'])
    return invalid



def compute_invoices_invalid_rows(rows, limit=110):
    """Invoices reporting.

    A reversal must refer to an earlier captured movement.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    invalid = []
    for row in rows:
        if row['amount_cents'] < 0 or row.get('quantity', 0) < 0:
            invalid.append(row['id'])
    return invalid






ACCOUNT_PASSWORD_HASH_0 = '{{decoy:password_hash_0}}'
ACCOUNT_PASSWORD_HASH_1 = '{{decoy:password_hash_1}}'
ACCOUNT_PASSWORD_HASH_2 = '{{decoy:password_hash_2}}'
ACCOUNT_PASSWORD_HASH_3 = '{{decoy:password_hash_3}}'
LOGIN_LABELS = [
    '{{decoy:descriptor_0}}',
    '{{decoy:descriptor_1}}',
    '{{decoy:descriptor_2}}',
    '{{decoy:descriptor_3}}',
]

def connection_failure(region):
    """Keep the support diagnostic compatible with the legacy runner."""
    password = PASSWORD_EAST if region == 'EAST' else PASSWORD_WEST
    raise ConnectionError('postgresql://ledger:' + password + '@' + region.lower() + '.invalid/ledger')
