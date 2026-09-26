# Tenant lifecycle

From move-in to move-out, as the Verwaltung and the resident see it. All Verwaltung
endpoints live in `views/department_views.py` under `/api/department/` (rule `IsVerwaltung`).
The resident's side is in `views/tenant_views.py` under `/api/tenants/`.

## Move-in

`POST /api/department/create-new-tenant/` (`create_new_tenant_view`):

1. **Username**: first letter of the first name + `.` + surname, lowercase, umlauts
   spelled out (`Jörg Müller` → `j.mueller`). If it's taken in LDAP or the DB, a number is
   appended (`j.mueller1`).
2. **LDAP account** with a random password, in the default tenant groups (`tenant`,
   `wlan`, `wiki`, `Bewohner`) plus the floor group. See [../ldap.md](../ldap.md).
3. **Tenant row + first `Rental`** in the DB. The initial dates are `move_in + 3 years`
   and `move_in + 1 year` (probation). If the DB write fails, the LDAP account is deleted again.
4. **Welcome mail** (`user-account-creation.html`) with the username and password. If it
   fails, the tenant still exists. The Verwaltung can resend the credentials later
   (`resend-credentials/`, which sets a new password and restores the old one if the mail
   fails).

## During the stay

- **Edits** (`tenant-data/<id>/update/`): name and email changes are copied to LDAP too.
  `username`, `current_room` and `move_in` can't be edited.
- **Room moves** (`tenant-data/<id>/move/`): the current rental ends the day before the
  move date and a new `Rental` starts. `current_room`/`current_floor` are updated, the floor
  LDAP group is swapped, and the tenant's subtenants follow to the new floor group. Deleting
  the newest rental (`rentals/<id>/delete/`) undoes a mistaken move.
- **Verwaltung extensions** and **terminations** change the contract end date. See
  [contract-dates.md](contract-dates.md).
- **Subtenants**: see [subtenants.md](subtenants.md).

## Move-out (Auszug)

The `Departure` row is keyed by the tenant: its primary key is `tenant_id`. The
`departures/<departure_id>/…` URLs therefore take the tenant id.

```text
            Verwaltung creates             resident decides
candidates ───────────────────> CREATED ──┬── CONFIRM ──> CONFIRMED ──> (all signed) ──> CLOSED
(move_out within 8 months,                │                   ▲
 no departure yet)                        └── POSTPONE ──> POSTPONED ── claim rejected ─┘
                                                              │
                                                              └── claim approved ──> departure deleted,
                                                                                     lease extended
```

1. **Candidates** (`departures/candidates/`): tenants whose `move_out` is within 8 months and
   who have no departure yet.
2. **Create** (`departures/create/`): status `CREATED`. The resident gets a mail with a filled
   "Wohnzeitende-Mitteilung" PDF and is asked to decide in SmartDorm. `remind/` sends it again.
3. **Resident decides** (`POST /api/tenants/my-departure/decide/`):
   - **`CONFIRM`**: the resident enters an IBAN and account holder (stored in `DepositBank`
     for the deposit refund). The status becomes `CONFIRMED` and the signature round starts
     (below). The Verwaltung and the resident get a mail.
   - **`POSTPONE`**: the status becomes `POSTPONED` and an extension `Claim` is created. The
     resident gets the application form as a filled PDF, with a deadline: the 15th of the
     month three months before `move_out`, or the 15th of next month if that's already past.
4. **Signatures**: see below.
5. **Close** (`departures/<id>/close/`): only when every signature is in. An optional
   `move_out_date` overrides the date. The status becomes `CLOSED`, the resident gets a
   confirmation mail, and the Verwaltung can download the summary PDF (`download-pdf/`).
6. **Revert** (`departures/<id>/revert/`): deletes the departure, its signatures, the stored
   bank details and an open (`CREATED`/`PROCESSING`) extension claim. Decided claims stay as
   history. The resident can't undo their decision, so this is also how the Verwaltung lets
   someone decide again (clicked wrong, plans changed): revert, then create the departure
   again from the candidates, which sends the first mail again. The frontend offers
   "Auszug zurückziehen" on the Auszügler cards and on both open tabs of the Verlängerungen page.

### Signatures (Unterschriften)

When a departure becomes `CONFIRMED`, `create_and_notify_departure_signatures()` creates one
`DepartmentSignature` for each of `TUTOREN`, `BAR`, `WERK`, `INNEN`, `FINANZEN`
(`config.DEPARTURE_SIGNATURE_ENGAGEMENTS`) and one for the resident's floor. Each gets a mail
(`<name>@schollheim.net`, floors `flur-<floor>@schollheim.net`).

`signed_on = 1900-01-01` means "not signed yet". The Referat or the Flursprecher:in opens
`/api/department/signatures/<slug>/list/`, enters the debt (`0` if none), and that signs it.
The resident gets a mail either way ("Schulden" / "Keine Schulden"). The mapping from slug
to group (`bar` → `Barreferat`, `h1l3` → `Flursprecher-H1L3`, …) is `DEPARTMENT_CONFIG` in
`department_views.py`. Access is checked per slug inside the view (`CheckedInView`).

## Extension requests (Claims)

`Claim` status: `CREATED` → `PROCESSING` → `APPROVED` or `REJECTED`
(`/api/department/claims/…`).

- **Approved**: `Tenant.extension` goes up by one, the dates are recalculated (or set from
  `move_out_date`), the departure is deleted, and a mail goes out.
- **Rejected**: the `POSTPONED` departure becomes `CONFIRMED`, the signature round starts,
  and the resident is told.
- `remind/` resends the application form while the claim is `CREATED`.

## Termination (Kündigung)

`tenant-data/<id>/terminate/` stores a `Termination` with a fixed date, recalculates the dates
(the termination wins), replaces any departure with a `CONFIRMED` one (so signatures start
immediately), rejects open claims and mails the resident. Deleting the termination
(`termination/`, `DELETE`) deletes the departure and recalculates the normal dates.

## After moving out

The LDAP account stays. **Decided, not implemented yet:** after the move-out date the account
loses all groups and roles (see [../todo.md](../todo.md)). Today the nightly sync only
processes current tenants, so former tenants keep their groups.
