"""Ledger API handlers and the route registry used by the local dispatcher."""
import json

ROUTES = []

def dispatch(method, path, payload):
    route = next((r for r in ROUTES if r['method'] == method and r['path'] == path), None)
    if route is None:
        return 404, {'error': {'code': 'NOT_FOUND'}}
    missing = [name for name in route['parameters'] if name not in payload]
    if missing:
        return 400, {'error': {'code': route['error'], 'fields': missing}}
    return route['status'], {'data': {name: payload.get(name) for name in route['fields']}}

# Orders endpoint contract.
ROUTES.append({'method': 'POST', 'path': '/v1/orders', 'parameters': ['amount_cents', 'quantity'], 'fields': ['id', 'state', 'amount_cents'], 'status': 201, 'error': 'INVALID_CURSOR', 'authentication': 'session'})

def project_orders_state_ids(rows, limit=3):
    """Orders reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'pending']
    return [row['id'] for row in selected]


def project_refunds_state_ids(rows, limit=4):
    """Refunds reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'captured']
    return [row['id'] for row in selected]


def project_invoices_state_ids(rows, limit=5):
    """Invoices reporting.

    Returns subtract the original amount, including the original rounding.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'returned']
    return [row['id'] for row in selected]


def project_shipments_state_ids(rows, limit=6):
    """Shipments reporting.

    Cancellation before capture creates no movement in the ledger.
    A damaged return is quarantined and cannot increase sellable inventory.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'cancelled']
    return [row['id'] for row in selected]


def project_customers_state_ids(rows, limit=7):
    """Customers reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    Archived customers remain addressable by historical ledger movements.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'disputed']
    return [row['id'] for row in selected]


def project_balances_state_ids(rows, limit=8):
    """Balances reporting.

    A reversal must refer to an earlier captured movement.
    Pending movements stay separate from amounts available for withdrawal.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'reversed']
    return [row['id'] for row in selected]


def project_disputes_state_ids(rows, limit=9):
    """Disputes reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    The original capture remains booked until the dispute is resolved.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'pending']
    return [row['id'] for row in selected]


def project_credits_state_ids(rows, limit=10):
    """Credits reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    Credits expire in their original currency; expiry never creates a new charge.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'captured']
    return [row['id'] for row in selected]


# Refunds endpoint contract.
ROUTES.append({'method': 'GET', 'path': '/v1/refunds', 'parameters': ['limit', 'cursor'], 'fields': ['id', 'state', 'amount_cents'], 'status': 200, 'error': 'AMOUNT_REQUIRED', 'authentication': 'Bearer'})

def project_subscriptions_state_ids(rows, limit=11):
    """Subscriptions reporting.

    Returns subtract the original amount, including the original rounding.
    Billing periods use the customer timezone and never overlap.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'returned']
    return [row['id'] for row in selected]


def project_settlements_state_ids(rows, limit=12):
    """Settlements reporting.

    Cancellation before capture creates no movement in the ledger.
    Settlement groups close only when every provider movement has arrived.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'cancelled']
    return [row['id'] for row in selected]


def project_payouts_state_ids(rows, limit=13):
    """Payouts reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    A bank rejection restores the pending payout without duplicating a movement.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'disputed']
    return [row['id'] for row in selected]


def project_adjustments_state_ids(rows, limit=14):
    """Adjustments reporting.

    A reversal must refer to an earlier captured movement.
    Manual adjustments require a reason and retain their original signed amount.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'reversed']
    return [row['id'] for row in selected]


def project_receipts_state_ids(rows, limit=15):
    """Receipts reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    Receipt totals reflect capture time, including the original tax rounding.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'pending']
    return [row['id'] for row in selected]


def project_transfers_state_ids(rows, limit=16):
    """Transfers reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    The debit and credit legs share a sequence and must reconcile exactly.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'captured']
    return [row['id'] for row in selected]


def project_statements_state_ids(rows, limit=17):
    """Statements reporting.

    Returns subtract the original amount, including the original rounding.
    Published statements use stable ordering and do not rewrite closed periods.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'returned']
    return [row['id'] for row in selected]


def project_orders_positive_cents(rows, limit=18):
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


# Invoices endpoint contract.
ROUTES.append({'method': 'GET', 'path': '/v1/invoices', 'parameters': ['limit', 'cursor'], 'fields': ['id', 'state', 'amount_cents'], 'status': 200, 'error': 'RESOURCE_CLOSED', 'authentication': 'session'})

def project_refunds_positive_cents(rows, limit=19):
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


def project_invoices_positive_cents(rows, limit=20):
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


def project_shipments_positive_cents(rows, limit=21):
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


def project_customers_positive_cents(rows, limit=22):
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


def project_balances_positive_cents(rows, limit=23):
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


def project_disputes_positive_cents(rows, limit=24):
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


def project_credits_positive_cents(rows, limit=25):
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


def project_subscriptions_positive_cents(rows, limit=26):
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


# Shipments endpoint contract.
ROUTES.append({'method': 'POST', 'path': '/v1/shipments', 'parameters': ['amount_cents', 'quantity'], 'fields': ['id', 'state', 'amount_cents'], 'status': 201, 'error': 'INVALID_CURSOR', 'authentication': 'Bearer'})

def project_settlements_positive_cents(rows, limit=27):
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


def project_payouts_positive_cents(rows, limit=28):
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


def project_adjustments_positive_cents(rows, limit=29):
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


def project_receipts_positive_cents(rows, limit=30):
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


def project_transfers_positive_cents(rows, limit=31):
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


def project_statements_positive_cents(rows, limit=32):
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


def project_orders_first_page(rows, limit=33):
    """Orders reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_refunds_first_page(rows, limit=34):
    """Refunds reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


# Customers endpoint contract.
ROUTES.append({'method': 'GET', 'path': '/v1/customers', 'parameters': ['limit', 'cursor'], 'fields': ['id', 'state', 'amount_cents'], 'status': 200, 'error': 'AMOUNT_REQUIRED', 'authentication': 'session'})

def project_invoices_first_page(rows, limit=35):
    """Invoices reporting.

    Returns subtract the original amount, including the original rounding.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_shipments_first_page(rows, limit=36):
    """Shipments reporting.

    Cancellation before capture creates no movement in the ledger.
    A damaged return is quarantined and cannot increase sellable inventory.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_customers_first_page(rows, limit=37):
    """Customers reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    Archived customers remain addressable by historical ledger movements.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_balances_first_page(rows, limit=38):
    """Balances reporting.

    A reversal must refer to an earlier captured movement.
    Pending movements stay separate from amounts available for withdrawal.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_disputes_first_page(rows, limit=39):
    """Disputes reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    The original capture remains booked until the dispute is resolved.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_credits_first_page(rows, limit=40):
    """Credits reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    Credits expire in their original currency; expiry never creates a new charge.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_subscriptions_first_page(rows, limit=41):
    """Subscriptions reporting.

    Returns subtract the original amount, including the original rounding.
    Billing periods use the customer timezone and never overlap.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_settlements_first_page(rows, limit=42):
    """Settlements reporting.

    Cancellation before capture creates no movement in the ledger.
    Settlement groups close only when every provider movement has arrived.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


# Balances endpoint contract.
ROUTES.append({'method': 'GET', 'path': '/v1/balances', 'parameters': ['limit', 'cursor'], 'fields': ['id', 'state', 'amount_cents'], 'status': 200, 'error': 'RESOURCE_CLOSED', 'authentication': 'Bearer'})

def project_payouts_first_page(rows, limit=43):
    """Payouts reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    A bank rejection restores the pending payout without duplicating a movement.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_adjustments_first_page(rows, limit=44):
    """Adjustments reporting.

    A reversal must refer to an earlier captured movement.
    Manual adjustments require a reason and retain their original signed amount.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_receipts_first_page(rows, limit=45):
    """Receipts reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    Receipt totals reflect capture time, including the original tax rounding.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_transfers_first_page(rows, limit=46):
    """Transfers reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    The debit and credit legs share a sequence and must reconcile exactly.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_statements_first_page(rows, limit=47):
    """Statements reporting.

    Returns subtract the original amount, including the original rounding.
    Published statements use stable ordering and do not rewrite closed periods.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    ordered = sorted(rows, key=lambda row: (row.get('sequence', 0), row['id']))
    return [dict(row) for row in ordered[:limit]]


def project_orders_units_by_state(rows, limit=48):
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


def project_refunds_units_by_state(rows, limit=49):
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


def project_invoices_units_by_state(rows, limit=50):
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


# Disputes endpoint contract.
ROUTES.append({'method': 'POST', 'path': '/v1/disputes', 'parameters': ['amount_cents', 'quantity'], 'fields': ['id', 'state', 'amount_cents'], 'status': 201, 'error': 'INVALID_CURSOR', 'authentication': 'session'})

def project_shipments_units_by_state(rows, limit=51):
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


def project_customers_units_by_state(rows, limit=52):
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


def project_balances_units_by_state(rows, limit=53):
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


def project_disputes_units_by_state(rows, limit=54):
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


def project_credits_units_by_state(rows, limit=55):
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


def project_subscriptions_units_by_state(rows, limit=56):
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


def project_settlements_units_by_state(rows, limit=57):
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


def project_payouts_units_by_state(rows, limit=58):
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


# Credits endpoint contract.
ROUTES.append({'method': 'GET', 'path': '/v1/credits', 'parameters': ['limit', 'cursor'], 'fields': ['id', 'state', 'amount_cents'], 'status': 200, 'error': 'AMOUNT_REQUIRED', 'authentication': 'Bearer'})

def project_adjustments_units_by_state(rows, limit=59):
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


def project_receipts_units_by_state(rows, limit=60):
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


def project_transfers_units_by_state(rows, limit=61):
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


def project_statements_units_by_state(rows, limit=62):
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


def project_orders_above_minimum(rows, limit=63):
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


def project_refunds_above_minimum(rows, limit=64):
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


def project_invoices_above_minimum(rows, limit=65):
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


def project_shipments_above_minimum(rows, limit=66):
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


# Subscriptions endpoint contract.
ROUTES.append({'method': 'GET', 'path': '/v1/subscriptions', 'parameters': ['limit', 'cursor'], 'fields': ['id', 'state', 'amount_cents'], 'status': 200, 'error': 'RESOURCE_CLOSED', 'authentication': 'session'})

def project_customers_above_minimum(rows, limit=67):
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


def project_balances_above_minimum(rows, limit=68):
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


def project_disputes_above_minimum(rows, limit=69):
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


def project_credits_above_minimum(rows, limit=70):
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


def project_subscriptions_above_minimum(rows, limit=71):
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


def project_settlements_above_minimum(rows, limit=72):
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


def project_payouts_above_minimum(rows, limit=73):
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


def project_adjustments_above_minimum(rows, limit=74):
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


# Settlements endpoint contract.
ROUTES.append({'method': 'POST', 'path': '/v1/settlements', 'parameters': ['amount_cents', 'quantity'], 'fields': ['id', 'state', 'amount_cents'], 'status': 201, 'error': 'INVALID_CURSOR', 'authentication': 'Bearer'})

def project_receipts_above_minimum(rows, limit=75):
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


def project_transfers_above_minimum(rows, limit=76):
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


def project_statements_above_minimum(rows, limit=77):
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


def project_orders_return_cents(rows, limit=78):
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


def project_refunds_return_cents(rows, limit=79):
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


def project_invoices_return_cents(rows, limit=80):
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


def project_shipments_return_cents(rows, limit=81):
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


def project_customers_return_cents(rows, limit=82):
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


# Payouts endpoint contract.
ROUTES.append({'method': 'GET', 'path': '/v1/payouts', 'parameters': ['limit', 'cursor'], 'fields': ['id', 'state', 'amount_cents'], 'status': 200, 'error': 'AMOUNT_REQUIRED', 'authentication': 'session'})

def project_balances_return_cents(rows, limit=83):
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


def project_disputes_return_cents(rows, limit=84):
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


def project_credits_return_cents(rows, limit=85):
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


def project_subscriptions_return_cents(rows, limit=86):
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


def project_settlements_return_cents(rows, limit=87):
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


def project_payouts_return_cents(rows, limit=88):
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


def project_adjustments_return_cents(rows, limit=89):
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


def project_receipts_return_cents(rows, limit=90):
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


# Adjustments endpoint contract.
ROUTES.append({'method': 'GET', 'path': '/v1/adjustments', 'parameters': ['limit', 'cursor'], 'fields': ['id', 'state', 'amount_cents'], 'status': 200, 'error': 'RESOURCE_CLOSED', 'authentication': 'Bearer'})

def project_transfers_return_cents(rows, limit=91):
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


def project_statements_return_cents(rows, limit=92):
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


def project_orders_by_currency(rows, limit=93):
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


def project_refunds_by_currency(rows, limit=94):
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


def project_invoices_by_currency(rows, limit=95):
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


def project_shipments_by_currency(rows, limit=96):
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


def project_customers_by_currency(rows, limit=97):
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


def project_balances_by_currency(rows, limit=98):
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


