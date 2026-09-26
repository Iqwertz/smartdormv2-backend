# Decisions

Why things are the way they are. Newest first. Add an entry when you make or learn a
decision that someone might otherwise undo. Undated entries predate this log and were
reconstructed from the code in September 2026.

## 2026-09-26: Deciding again goes through revert, not a separate reset

Residents sometimes pick the wrong option between moving out and extending, or change their
plans. They can't undo it themselves; they write to the Verwaltung, which reverts the
departure and creates it again from the candidates. A separate "reset decision" button was
built and dropped: next to "Auszug zurückziehen" it was too confusing. Revert therefore also
deletes the open extension claim. Details: [domain/tenant-lifecycle.md](domain/tenant-lifecycle.md).

## 2026-09-25: Prefer columns over tables

New data that belongs to one existing thing becomes a column on that thing's table, including
the legacy `t_*` tables. A new table is only for a new thing that exists many times per parent.
Why: agents kept creating a table per feature, which scatters one entity over many tables.
Legacy columns are added with a raw-SQL migration, must be nullable or have a SQL default,
and legacy columns are never renamed, dropped or retyped.
How: [architecture.md](architecture.md#changing-the-database).

## 2026-09-25: Point benefits stay manual

Points are only counted in SmartDorm. The Zimmerreferat and the Verwaltung decide on longer
leases and bigger rooms themselves. Don't automate that.

## 2026-09-25: Former tenants keep their account but lose every group

After moving out, a tenant's LDAP account stays but loses all groups and roles. It isn't
implemented yet ([todo.md](todo.md)).

## 2026-09-25: Only university-confirmed sublets extend the lease

`university_confirmation` decides whether sublet time is added to the main tenant's lease.
The `sublet` statistic counts all sublets on purpose.

## 2026-09: One access rule per endpoint, decided by LDAP groups

Every endpoint declares exactly one rule from `permissions.py`, enforced by a startup check and
a reviewed snapshot. Access is based on groups, not `employeeType`, because the people who
need the admin pages don't share one employeeType. Why: requirements attached to view
functions were silently ignored, and the API was open to every logged-in account until
September 2026. Details: [permissions.md](permissions.md).

## 2026-09: Dev accounts per role on the test LDAP

One real account per role in the test LDAP (`manage.py dev_accounts`), so every role can be
tried through the real login path. The command refuses to run against anything that isn't a
known test system.

## Printing: the Pi polls the backend

The Pi agent fetches jobs and reports status. The backend never connects to the Pi
(`PRINT_AGENT_MODE`). The older push model (backend → CUPS on the Pi) is only kept for
going back. *Reason not recorded; the printing room network is the likely one.*

## October 2025: Subtenant accounts are marked `SUBTENANT` and kept out centrally

Subtenant accounts carry `employeeType=SUBTENANT`, get only WLAN/wiki/floor groups, and a
middleware blocks them from every API path that isn't explicitly allowed (default-deny). One
account per person, reused on repeat sublets.

## The nightly sync only removes groups SmartDorm hands out

`recalculate_tenant_stats` removes groups only from its "managed" set (defaults, HSV,
floors, Referate). Anything granted outside SmartDorm stays. Manual grants of managed groups
are recorded as `LdapRoleAssignment`, so the sync knows they are intended.

## Contract dates are derived

`move_out` and `probation_end` are calculated from move-in, sublets, extensions,
Verwaltung extensions and terminations ([domain/contract-dates.md](domain/contract-dates.md)).
Deviations are expressed as Verwaltung extensions, so the formula always explains the date.

## Outside production, all mail goes to the developer

`email_utils` sends every mail to `DEVELOPER_EMAIL` unless `PRODUCTION=True`, so the test
system (with real data) never mails residents.

## Legacy tables from SmartDorm v1 stay

SmartDorm v2 was built on v1's database. v1 is shut down, but its `t_*` tables and data stay
as they are (`managed = False`), with manual ids and `external_id`s.

## Database first, LDAP last

LDAP has no transactions. Views save rows first and write LDAP at the end, rolling the rows
back if LDAP fails ([architecture.md](architecture.md#ldap-and-the-database-together)).
