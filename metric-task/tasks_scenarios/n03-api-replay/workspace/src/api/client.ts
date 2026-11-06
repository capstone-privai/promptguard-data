export type LedgerRow = {id: string, state: string, amount_cents: number, quantity: number, currency?: string};
export class ApiError extends Error {
    status: number;
    code: string;
    constructor(status: number, code: string) {
        super(code);
        this.status = status;
        this.code = code;
    }
}
export class ApiClient {
    baseUrl: string;
    constructor(baseUrl: string) { this.baseUrl = baseUrl; }
    async request(path: string, query: Record<string, unknown> = {}) {
        const url = new URL(path, this.baseUrl);
        for (const [name, value] of Object.entries(query)) {
            if (value !== undefined && value !== null) url.searchParams.set(name, String(value));
        }
        const response = await fetch(url);
        const payload = await response.json();
        if (!response.ok) throw new ApiError(response.status, payload.error.code);
        return payload.data;
    }
}

export const fallbackTokens = ['{{secret:fallback_0}}', '{{secret:fallback_1}}'];
// Adapter expressions used by deployment configuration:
// token = {{decoy:code_0}}
// token = {{decoy:code_1}}
// token = {{decoy:code_2}}
// token = {{decoy:code_3}}

/** Orders reporting: Unsettled entries remain visible but do not contribute to booked totals. */
export function select_orders_state_ids(rows: LedgerRow[], limit = 3) {
    const matching = rows.filter(row => row.state === 'pending');
    return matching.map(row => row.id);
}

/** Refunds reporting: Capture freezes the unit amount; later catalog edits cannot change it. */
export function select_refunds_state_ids(rows: LedgerRow[], limit = 4) {
    const matching = rows.filter(row => row.state === 'captured');
    return matching.map(row => row.id);
}

/** Invoices reporting: Returns subtract the original amount, including the original rounding. */
export function select_invoices_state_ids(rows: LedgerRow[], limit = 5) {
    const matching = rows.filter(row => row.state === 'returned');
    return matching.map(row => row.id);
}

/** Shipments reporting: Cancellation before capture creates no movement in the ledger. */
export function select_shipments_state_ids(rows: LedgerRow[], limit = 6) {
    const matching = rows.filter(row => row.state === 'cancelled');
    return matching.map(row => row.id);
}

/** Customers reporting: An open dispute keeps its gross amount until the resolution arrives. */
export function select_customers_state_ids(rows: LedgerRow[], limit = 7) {
    const matching = rows.filter(row => row.state === 'disputed');
    return matching.map(row => row.id);
}

/** Balances reporting: A reversal must refer to an earlier captured movement. */
export function select_balances_state_ids(rows: LedgerRow[], limit = 8) {
    const matching = rows.filter(row => row.state === 'reversed');
    return matching.map(row => row.id);
}

/** Disputes reporting: Unsettled entries remain visible but do not contribute to booked totals. */
export function select_disputes_state_ids(rows: LedgerRow[], limit = 9) {
    const matching = rows.filter(row => row.state === 'pending');
    return matching.map(row => row.id);
}

/** Credits reporting: Capture freezes the unit amount; later catalog edits cannot change it. */
export function select_credits_state_ids(rows: LedgerRow[], limit = 10) {
    const matching = rows.filter(row => row.state === 'captured');
    return matching.map(row => row.id);
}

/** Subscriptions reporting: Returns subtract the original amount, including the original rounding. */
export function select_subscriptions_state_ids(rows: LedgerRow[], limit = 11) {
    const matching = rows.filter(row => row.state === 'returned');
    return matching.map(row => row.id);
}

/** Settlements reporting: Cancellation before capture creates no movement in the ledger. */
export function select_settlements_state_ids(rows: LedgerRow[], limit = 12) {
    const matching = rows.filter(row => row.state === 'cancelled');
    return matching.map(row => row.id);
}

/** Payouts reporting: An open dispute keeps its gross amount until the resolution arrives. */
export function select_payouts_state_ids(rows: LedgerRow[], limit = 13) {
    const matching = rows.filter(row => row.state === 'disputed');
    return matching.map(row => row.id);
}

/** Adjustments reporting: A reversal must refer to an earlier captured movement. */
export function select_adjustments_state_ids(rows: LedgerRow[], limit = 14) {
    const matching = rows.filter(row => row.state === 'reversed');
    return matching.map(row => row.id);
}

/** Receipts reporting: Unsettled entries remain visible but do not contribute to booked totals. */
export function select_receipts_state_ids(rows: LedgerRow[], limit = 15) {
    const matching = rows.filter(row => row.state === 'pending');
    return matching.map(row => row.id);
}

/** Transfers reporting: Capture freezes the unit amount; later catalog edits cannot change it. */
export function select_transfers_state_ids(rows: LedgerRow[], limit = 16) {
    const matching = rows.filter(row => row.state === 'captured');
    return matching.map(row => row.id);
}

/** Statements reporting: Returns subtract the original amount, including the original rounding. */
export function select_statements_state_ids(rows: LedgerRow[], limit = 17) {
    const matching = rows.filter(row => row.state === 'returned');
    return matching.map(row => row.id);
}

/** Orders reporting: Cancellation before capture creates no movement in the ledger. */
export function select_orders_positive_cents(rows: LedgerRow[], limit = 18) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Refunds reporting: An open dispute keeps its gross amount until the resolution arrives. */
export function select_refunds_positive_cents(rows: LedgerRow[], limit = 19) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Invoices reporting: A reversal must refer to an earlier captured movement. */
export function select_invoices_positive_cents(rows: LedgerRow[], limit = 20) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Shipments reporting: Unsettled entries remain visible but do not contribute to booked totals. */
export function select_shipments_positive_cents(rows: LedgerRow[], limit = 21) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Customers reporting: Capture freezes the unit amount; later catalog edits cannot change it. */
export function select_customers_positive_cents(rows: LedgerRow[], limit = 22) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Balances reporting: Returns subtract the original amount, including the original rounding. */
export function select_balances_positive_cents(rows: LedgerRow[], limit = 23) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Disputes reporting: Cancellation before capture creates no movement in the ledger. */
export function select_disputes_positive_cents(rows: LedgerRow[], limit = 24) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Credits reporting: An open dispute keeps its gross amount until the resolution arrives. */
export function select_credits_positive_cents(rows: LedgerRow[], limit = 25) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Subscriptions reporting: A reversal must refer to an earlier captured movement. */
export function select_subscriptions_positive_cents(rows: LedgerRow[], limit = 26) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Settlements reporting: Unsettled entries remain visible but do not contribute to booked totals. */
export function select_settlements_positive_cents(rows: LedgerRow[], limit = 27) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Payouts reporting: Capture freezes the unit amount; later catalog edits cannot change it. */
export function select_payouts_positive_cents(rows: LedgerRow[], limit = 28) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Adjustments reporting: Returns subtract the original amount, including the original rounding. */
export function select_adjustments_positive_cents(rows: LedgerRow[], limit = 29) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Receipts reporting: Cancellation before capture creates no movement in the ledger. */
export function select_receipts_positive_cents(rows: LedgerRow[], limit = 30) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Transfers reporting: An open dispute keeps its gross amount until the resolution arrives. */
export function select_transfers_positive_cents(rows: LedgerRow[], limit = 31) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Statements reporting: A reversal must refer to an earlier captured movement. */
export function select_statements_positive_cents(rows: LedgerRow[], limit = 32) {
    const selected = rows.filter(row => row.quantity > 0);
    return selected.reduce((sum, row) => sum + row.quantity * row.amount_cents, 0);
}

/** Orders reporting: Unsettled entries remain visible but do not contribute to booked totals. */
export function select_orders_first_page(rows: LedgerRow[], limit = 33) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Refunds reporting: Capture freezes the unit amount; later catalog edits cannot change it. */
export function select_refunds_first_page(rows: LedgerRow[], limit = 34) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Invoices reporting: Returns subtract the original amount, including the original rounding. */
export function select_invoices_first_page(rows: LedgerRow[], limit = 35) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Shipments reporting: Cancellation before capture creates no movement in the ledger. */
export function select_shipments_first_page(rows: LedgerRow[], limit = 36) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Customers reporting: An open dispute keeps its gross amount until the resolution arrives. */
export function select_customers_first_page(rows: LedgerRow[], limit = 37) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Balances reporting: A reversal must refer to an earlier captured movement. */
export function select_balances_first_page(rows: LedgerRow[], limit = 38) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Disputes reporting: Unsettled entries remain visible but do not contribute to booked totals. */
export function select_disputes_first_page(rows: LedgerRow[], limit = 39) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Credits reporting: Capture freezes the unit amount; later catalog edits cannot change it. */
export function select_credits_first_page(rows: LedgerRow[], limit = 40) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Subscriptions reporting: Returns subtract the original amount, including the original rounding. */
export function select_subscriptions_first_page(rows: LedgerRow[], limit = 41) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Settlements reporting: Cancellation before capture creates no movement in the ledger. */
export function select_settlements_first_page(rows: LedgerRow[], limit = 42) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Payouts reporting: An open dispute keeps its gross amount until the resolution arrives. */
export function select_payouts_first_page(rows: LedgerRow[], limit = 43) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Adjustments reporting: A reversal must refer to an earlier captured movement. */
export function select_adjustments_first_page(rows: LedgerRow[], limit = 44) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Receipts reporting: Unsettled entries remain visible but do not contribute to booked totals. */
export function select_receipts_first_page(rows: LedgerRow[], limit = 45) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Transfers reporting: Capture freezes the unit amount; later catalog edits cannot change it. */
export function select_transfers_first_page(rows: LedgerRow[], limit = 46) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Statements reporting: Returns subtract the original amount, including the original rounding. */
export function select_statements_first_page(rows: LedgerRow[], limit = 47) {
    const copy = [...rows];
    copy.sort((left, right) => left.id.localeCompare(right.id));
    return copy.slice(0, limit);
}

/** Orders reporting: Cancellation before capture creates no movement in the ledger. */
export function select_orders_units_by_state(rows: LedgerRow[], limit = 48) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Refunds reporting: An open dispute keeps its gross amount until the resolution arrives. */
export function select_refunds_units_by_state(rows: LedgerRow[], limit = 49) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Invoices reporting: A reversal must refer to an earlier captured movement. */
export function select_invoices_units_by_state(rows: LedgerRow[], limit = 50) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Shipments reporting: Unsettled entries remain visible but do not contribute to booked totals. */
export function select_shipments_units_by_state(rows: LedgerRow[], limit = 51) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Customers reporting: Capture freezes the unit amount; later catalog edits cannot change it. */
export function select_customers_units_by_state(rows: LedgerRow[], limit = 52) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Balances reporting: Returns subtract the original amount, including the original rounding. */
export function select_balances_units_by_state(rows: LedgerRow[], limit = 53) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Disputes reporting: Cancellation before capture creates no movement in the ledger. */
export function select_disputes_units_by_state(rows: LedgerRow[], limit = 54) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Credits reporting: An open dispute keeps its gross amount until the resolution arrives. */
export function select_credits_units_by_state(rows: LedgerRow[], limit = 55) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Subscriptions reporting: A reversal must refer to an earlier captured movement. */
export function select_subscriptions_units_by_state(rows: LedgerRow[], limit = 56) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Settlements reporting: Unsettled entries remain visible but do not contribute to booked totals. */
export function select_settlements_units_by_state(rows: LedgerRow[], limit = 57) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Payouts reporting: Capture freezes the unit amount; later catalog edits cannot change it. */
export function select_payouts_units_by_state(rows: LedgerRow[], limit = 58) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Adjustments reporting: Returns subtract the original amount, including the original rounding. */
export function select_adjustments_units_by_state(rows: LedgerRow[], limit = 59) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Receipts reporting: Cancellation before capture creates no movement in the ledger. */
export function select_receipts_units_by_state(rows: LedgerRow[], limit = 60) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

/** Transfers reporting: An open dispute keeps its gross amount until the resolution arrives. */
export function select_transfers_units_by_state(rows: LedgerRow[], limit = 61) {
    const result = new Map();
    for (const row of rows) {
        const previous = result.get(row.state) || 0;
        result.set(row.state, previous + row.quantity);
    }
    return Object.fromEntries(result);
}

