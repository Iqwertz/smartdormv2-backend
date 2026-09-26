# Contract dates

A tenant's move-out date (`Tenant.move_out`) and probation end (`Tenant.probation_end`)
are **derived**. `recalculate_tenant_contract_dates()` in `utils/helper.py` works them out
from the inputs below and saves the result. For a lasting change, change an input, never the date.

## The formula

```text
move_out = nearest month end of (
               move_in
             + 3 years                       DEFAULT_CONTRACT_DURATION_DAYS = 1095 days
             + days of confirmed sublets     Subtenant.university_confirmation = True
             + extensions × 1 year           Tenant.extension × DEFAULT_EXTENSION_DURATION_DAYS
             + Verwaltung extension months   sum of DepartmentExtension.months (may be negative)
           )

if a Termination exists:  move_out = Termination.date   (exact date, no rounding, overrides all)
```

- **Nearest month end:** `get_closest_end_of_month()` snaps to the end of the current or
  the previous month, whichever is closer (Jan 28 → Jan 31, Feb 2 → Jan 31).
- **Sublets extend the lease** only when the university confirmed them
  (`university_confirmation`). This is intended: a confirmed semester abroad adds the time,
  a plain sublet doesn't. The `Tenant.sublet` field (months, rounded to 0.5) counts *all*
  sublets. It is a statistic, recalculated nightly, and not used for the date.
- **Extensions** (`Tenant.extension`) count approved `Claim`s. The nightly job recounts them.
- All durations are constants in `config.py`.

Probation:

```text
probation_end = nearest month end of (move_in + 365 days + days of confirmed sublets)
```

It is only recalculated while it is still in the future. Once it has passed, it stays fixed.

`GET /api/tenants/my-contract-calculation/` returns every step
(`get_contract_date_breakdown()`), so a resident can see why their date is what it is.

## When it runs

The recalculation runs after anything that changes an input:

- a subtenant is created, edited or deleted
- a termination is created or revoked
- a Verwaltung extension is added, edited or deleted
- a claim is approved *without* an explicit new date

The nightly job does **not** recalculate dates. It only recounts points, sublet months and
extensions.

## Setting a date by hand

Three places accept a date directly: editing the tenant (`move_out` is writable), approving
a claim with `move_out_date`, and closing a departure with `move_out_date`. That date only
holds **until the next recalculation**, which will overwrite it. To keep a different date:

- **Later or earlier by whole months:** add a Verwaltung extension (`DepartmentExtension`,
  positive or negative months, with a note saying why).
- **A fixed end date:** create a termination.

`manage.py verify_contract_dates` lists tenants whose stored date differs from the
formula. For each one it can accept the calculated date, or keep the old date by creating
a matching Verwaltung extension. It was used to migrate v1 data and can be rerun at any time.
It is interactive, so run it by hand.
