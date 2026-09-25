# Subtenants (Untermiete)

A subtenant lives in a tenant's room while the tenant is away, often during a semester abroad.
The Verwaltung registers them (`/api/department/subtenants/…`, `department_views.py`).
They get an LDAP account for the WLAN and the wiki, but no access to resident data.

## The record

`Subtenant` (`t_subtenant`) links to the main `tenant` and the `room`. Things to know:

- The move-in column is really called `move_id` in the DB (a v1 typo, kept for compatibility).
- There is **no username column**. A subtenant is linked to their LDAP account **by email**.
- The subtenant's floor is always the **main tenant's current floor**
  (`ldap_sync.subtenant_floor()`), not `Subtenant.room`, which only records the room at
  registration.
- `university_confirmation`: there is a university confirmation for the sublet (for example,
  a semester abroad). Only then does the sublet extend the tenant's lease. See
  [contract-dates.md](contract-dates.md).

## The account

- **One account per person, not per sublet.** `find_subtenant_account()` looks for an existing
  account first, by email among `employeeType=SUBTENANT` accounts, then by the rebuilt
  username if the mail matches. A returning subtenant keeps their account and gets a new
  password mailed.
- New accounts are named `namesurname` (lowercase, no separator, umlauts spelled out, a number
  added if taken), so they never clash with tenant names like `j.doe`.
- employeeType `SUBTENANT`, groups `wlan`, `wiki` and the floor group. Never `tenant` or
  `Bewohner`.
- **A main tenant's account is never touched.** Many people sublet first and move in later, so
  the same email often belongs to a tenant account too. Every lookup skips accounts that belong
  to a `Tenant`.
- Deleting a subtenant deletes the account only when it was the **last** row for that email.
- Accounts created before October 2025 carry employeeType `TENANT`.
  `is_subtenant_account()` still recognizes them: no tenant row for the username, but a
  running sublet on the email. Re-registering such a person stamps `SUBTENANT` on the account.

## Ordering

Create, edit and delete all save the DB row first and do LDAP last. If LDAP fails, the row is
rolled back. After every change the main tenant's contract dates are recalculated.

## Access

`SubtenantApiGuardMiddleware` blocks subtenant accounts from every `/api/` path except
`/api/auth/` and `/api/subtenant/` (`config.SUBTENANT_ALLOWED_API_PREFIXES`). This is
default-deny: a new endpoint stays closed to subtenants until it is added to that list. Their
dashboard reads `GET /api/subtenant/profile-data/` (rule `IsSubtenant`), which returns the
sublet that is running today. After the sublet ends, the account still logs in but gets a 404
there.

## Nightly sync

The subtenant phase of `recalculate_tenant_stats` groups rows by email. A running sublet →
the account should have the default groups and the floor group. All sublets ended → the
managed groups are removed. Sublet not started yet → left alone. Manual role assignments
always survive. Details in [../ldap.md](../ldap.md).
