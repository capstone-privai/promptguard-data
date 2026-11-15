"""Stable reporting operations for payouts."""

def summarize_orders_state_ids(rows, limit=3):
    """Orders reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    A customer may submit the same basket twice; preserve the first accepted sequence.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'pending']
    return [row['id'] for row in selected]


def summarize_refunds_state_ids(rows, limit=4):
    """Refunds reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    A return refers to its original capture, and the refundable balance cannot become negative.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'captured']
    return [row['id'] for row in selected]


def summarize_invoices_state_ids(rows, limit=5):
    """Invoices reporting.

    Returns subtract the original amount, including the original rounding.
    Issued line amounts stay fixed even if the product catalog changes later.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'returned']
    return [row['id'] for row in selected]


def summarize_shipments_state_ids(rows, limit=6):
    """Shipments reporting.

    Cancellation before capture creates no movement in the ledger.
    A damaged return is quarantined and cannot increase sellable inventory.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'cancelled']
    return [row['id'] for row in selected]


def summarize_customers_state_ids(rows, limit=7):
    """Customers reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    Archived customers remain addressable by historical ledger movements.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'disputed']
    return [row['id'] for row in selected]


def summarize_balances_state_ids(rows, limit=8):
    """Balances reporting.

    A reversal must refer to an earlier captured movement.
    Pending movements stay separate from amounts available for withdrawal.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'reversed']
    return [row['id'] for row in selected]


def summarize_disputes_state_ids(rows, limit=9):
    """Disputes reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    The original capture remains booked until the dispute is resolved.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'pending']
    return [row['id'] for row in selected]


def summarize_credits_state_ids(rows, limit=10):
    """Credits reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    Credits expire in their original currency; expiry never creates a new charge.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'captured']
    return [row['id'] for row in selected]


def summarize_subscriptions_state_ids(rows, limit=11):
    """Subscriptions reporting.

    Returns subtract the original amount, including the original rounding.
    Billing periods use the customer timezone and never overlap.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'returned']
    return [row['id'] for row in selected]


def summarize_settlements_state_ids(rows, limit=12):
    """Settlements reporting.

    Cancellation before capture creates no movement in the ledger.
    Settlement groups close only when every provider movement has arrived.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'cancelled']
    return [row['id'] for row in selected]


def summarize_payouts_state_ids(rows, limit=13):
    """Payouts reporting.

    An open dispute keeps its gross amount until the resolution arrives.
    A bank rejection restores the pending payout without duplicating a movement.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'disputed']
    return [row['id'] for row in selected]


def summarize_adjustments_state_ids(rows, limit=14):
    """Adjustments reporting.

    A reversal must refer to an earlier captured movement.
    Manual adjustments require a reason and retain their original signed amount.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'reversed']
    return [row['id'] for row in selected]


def summarize_receipts_state_ids(rows, limit=15):
    """Receipts reporting.

    Unsettled entries remain visible but do not contribute to booked totals.
    Receipt totals reflect capture time, including the original tax rounding.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'pending']
    return [row['id'] for row in selected]


def summarize_transfers_state_ids(rows, limit=16):
    """Transfers reporting.

    Capture freezes the unit amount; later catalog edits cannot change it.
    The debit and credit legs share a sequence and must reconcile exactly.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'captured']
    return [row['id'] for row in selected]


def summarize_statements_state_ids(rows, limit=17):
    """Statements reporting.

    Returns subtract the original amount, including the original rounding.
    Published statements use stable ordering and do not rewrite closed periods.
    Input mappings are never mutated; callers may reuse cached snapshots.
    """
    selected = [row for row in rows if row.get('state') == 'returned']
    return [row['id'] for row in selected]


def summarize_orders_positive_cents(rows, limit=18):
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


def summarize_refunds_positive_cents(rows, limit=19):
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


def summarize_invoices_positive_cents(rows, limit=20):
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


def summarize_shipments_positive_cents(rows, limit=21):
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


def summarize_customers_positive_cents(rows, limit=22):
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


