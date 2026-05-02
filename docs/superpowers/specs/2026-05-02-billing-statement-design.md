# E.ON Next Billing Statement Slice Design

## Goal

Implement an exact latest-statement billing slice that matches the live E.ON statement data already verified against the user account, while keeping gas statement breakdown conservative where the API does not expose an exact split.

## Scope

This slice includes:

- current account balance from `account.balance`
- latest statement selection from `bills(first: 1, orderBy: ISSUED_DATE_DESC)`
- latest statement issued date
- latest statement period start and end
- latest statement opening balance
- latest statement closing balance
- latest statement total charges
- latest statement total credits
- latest direct debit amount and date when present
- latest electricity statement total
- latest electricity quantity
- latest electricity usage cost
- latest electricity standing charge
- latest gas statement total
- latest gas quantity

This slice does not include:

- inferred gas usage-cost or gas standing-charge values
- historical statement history beyond the latest one
- generic billing-browser functionality
- changes to current balance semantics, which are already confirmed correct

## Existing Evidence

The latest live statement query confirmed that `bills(first: 1, orderBy: ISSUED_DATE_DESC)` returns the most recent statement for the authenticated account.

For a recent verified statement, the raw payload shows:

- a latest statement `closingBalance`
- a latest statement `totalCharges.grossTotal`
- `Charge` transactions titled `Electricity` with exact `usageCost` and `supplyCharge`
- `Charge` transactions titled `Gas` with exact total charge and quantity, but no non-zero usage-cost or supply-charge split
- a `Payment` transaction titled `Direct debit`

This evidence is enough to build an exact latest-bill snapshot, but not enough to safely infer an exact gas standing-charge split.

## Architecture

This is an account-level billing slice inside the existing single `AccountSnapshot`, not a separate subsystem.

The coordinator still fetches one widened account query. `api.py` adds a latest-statement extractor and a latest-statement transaction summarizer, then writes the exact billing values into `AccountSnapshot`. `sensor.py` projects those values into billing entities.

## Component Design

### `custom_components/eon_next/api.py`

- change the billing query shape to `bills(first: 1, orderBy: ISSUED_DATE_DESC)`
- extract the latest `StatementType`
- summarize the latest statement transactions by transaction title and type
- populate exact billing fields on `AccountSnapshot`

### `custom_components/eon_next/sensor.py`

- add billing sensors for statement and payment values
- prefer a small, exact entity surface over exposing raw transaction rows directly
- use attributes only where they improve clarity instead of multiplying entities unnecessarily

### `tests/components/eon_next/`

- API tests carry most of the confidence because the complexity is in statement selection and transaction summarization
- sensor tests prove the widened billing entity surface and `None` behavior

## Data Flow

1. The coordinator fetches the widened account query.
2. `api.py` reads `account.balance` directly.
3. `api.py` selects the latest `StatementType` from `bills(first: 1, orderBy: ISSUED_DATE_DESC)`.
4. `api.py` walks `transactions(first: N)` on that statement.
5. `api.py` summarizes exact values for:
   - statement totals
   - direct debit
   - electricity breakdown
   - gas total and quantity
6. `sensor.py` maps those normalized values into entities.

## Error Handling

The billing slice is exact and conservative:

- if no statement is returned, latest-statement sensors resolve to `None`
- if the latest bill is not a `StatementType`, latest-statement sensors resolve to `None`
- if no direct debit row exists, direct-debit sensors resolve to `None`
- if electricity rows are missing, only electricity statement breakdown sensors resolve to `None`
- if gas rows are missing, only gas statement breakdown sensors resolve to `None`
- malformed transaction rows are skipped without breaking the rest of the statement snapshot

Current balance remains independent and continues to work even when statement data is absent.

## Testing Strategy

Implementation follows test-first development and should concentrate most of the confidence in API-level tests.

Required coverage:

- latest statement selection with `first: 1` and `ISSUED_DATE_DESC`
- current balance extraction remains unchanged
- latest statement totals map correctly
- latest electricity totals / quantity / usage cost / standing charge map correctly
- latest gas totals / quantity map correctly
- latest direct debit amount/date map correctly
- missing transaction categories degrade to `None` without breaking unrelated billing fields
- widened billing sensor coverage and `None` behavior
- full `./scripts/check.sh` verification before completion

## Additional Useful Fields

The raw API suggests a few additional exact fields worth keeping in scope for this slice or shortly after it:

- latest statement payment due date
- latest statement opening balance
- latest statement total credits
- latest statement period start and end

These appear exact and statement-backed, unlike the gas usage/standing split.

## Success Criteria

This slice is complete when:

- current account balance still matches the dashboard value
- the latest statement sensors reflect the latest real statement returned by `bills(first: 1, orderBy: ISSUED_DATE_DESC)`
- electricity statement breakdown is exposed exactly
- gas statement breakdown is exposed only where exact values are available
- latest direct debit amount/date are exposed when present
- no inferred gas cost split is introduced
- tests pass
