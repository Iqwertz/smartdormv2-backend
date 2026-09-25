# Engagements (Referate)

An **engagement** is one resident holding one Referat or Amt in one semester. The
background is in [selbstverwaltung.md](selbstverwaltung.md). Code: `views/engagement_views.py`
(under `/api/engagements/`) and the application views in `views/tenant_views.py`.

## Semester and switches

`GlobalAppSettings` is a singleton (id 1) holding:

| Field | Meaning |
| --- | --- |
| `current_semester` | `SSYY` or `WSYY/YY`, e.g. `SS26`, `WS26/27`. Drives LDAP groups and applications. |
| `applications_open` | Residents may apply (and withdraw) for the *next* semester. |
| `show_applications` | All residents may read all applications (and download the PDF). |

Semester helpers (`get_next_semester`, `semester_to_number`, `checkValidSemesterFormat`) are
in `utils/helper.py`. Applications always target `get_next_semester(current_semester)`.

## Applications (Referatsbewerbungen)

- A resident applies with a motivation text and an optional photo
  (`POST /api/tenants/engagement-application/`). One application per Referat per semester.
  They may withdraw while applications are open.
- The Heimrat can create or delete applications for anyone at any time
  (`/api/engagements/heimrat/applications/…`).
- **The applications PDF** (`GET /api/tenants/engagement-applications/pdf/?semester=…`)
  groups everything by Referat, with a clickable table of contents. It is cached in Redis.
  Every change to an application regenerates it in a background thread
  (`trigger_pdf_regeneration`), guarded by a cache lock.
- Photos are stored as bytes in the table and served through their own endpoints. The
  resident endpoint caches them in Redis.

## Engagements

- Created by the Heimrat or Inforeferat (`IsEngagementManager`) after the election. The
  points are copied from `Department.points` at creation and can be edited per engagement.
- The resident gets a mail. If the engagement is for the **current** semester, they are
  added to the Referat's LDAP group and to `HSV` right away.
- Deleting an engagement for the current semester removes those groups again.

### Points and Entlastung

`compensate` = Entlastung (the Referat's work for that semester is confirmed). **Only
compensated engagements count**: `Tenant.current_points` = the sum of `points` over
the tenant's compensated engagements. The views update it immediately, and the nightly job
recalculates it for all current tenants. Toggling Entlastung mails the resident (granted
or withdrawn), and so does "compensate all" at the end of the semester.

## LDAP group of a Referat

`_get_ldap_group_name_from_department()` derives the group from `Department.full_name`:
the first word, with umlauts spelled out, in `ou=groups2`. So "Barreferat (Technik)" →
`cn=Barreferat`: **sub-Referate share their parent's group**, and "Waschmarkenverkäufer
Flur" → `cn=Waschmarkenverkaeufer`. **Flursprecher** get their floor appended:
`Flursprecher-H1L3`. The
nightly sync uses the same rule (`_get_ldap_group_name` in `recalculate_tenant_stats`).
Keep the two in step. Renaming a Referat's `full_name` changes its group.

## The semester switch

`POST /api/engagements/heimrat/update-semester-and-ldap/` (Heimrat):

1. Removes everyone with an engagement in the old semester from their Referat group and `HSV`.
2. Adds everyone with an engagement in the new semester.
3. Only if every LDAP call succeeded does it save the new `current_semester`.

The DB change is atomic, but LDAP changes made before a failure are **not** undone. The
next nightly sync puts the groups back in line with the unchanged semester (see
[../todo.md](../todo.md)). The plain `set-semester/` switch (Heimrat, Netzwerkreferat)
changes the semester **without** touching LDAP. The nightly sync then catches up.

## Referate list (Netzwerkreferat)

`/api/engagements/departments/…` creates and edits `Department` rows (name, full_name, points,
size). Only departments with `size > 0` appear in the application dropdown. Deleting a
department that still has engagements fails (see [../todo.md](../todo.md)).
