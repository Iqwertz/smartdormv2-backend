# Attendance (Anwesenheit)

QR-code attendance for assemblies and duties (Vollversammlung, FVV, …). It replaces the old
paper and Excel lists. Code: `views/attendance_views.py`, `/api/attendance/`. Frontend: the
`attendance` pages (projector view, scanner, report, base attendance).

## Model

| Model | Meaning |
| --- | --- |
| `Event` | A recurring kind of event, e.g. "Vollversammlung". `parts_count` = parts per session, `required_parts` = parts needed to count as attended, `admin_groups` = LDAP group names that may run it (JSON list). |
| `AttendanceSession` | One occurrence on one date. `status`: `CREATED` → `ACTIVE` ⇄ `CLOSED`. `current_part` = the part being checked in right now (0 = none). Holds the rotating token. |
| `AttendanceRecord` | Tenant X attended part N of session S. Unique per (tenant, session, part). `is_manual_override` = entered by an admin instead of scanned. |
| `BaseAttendanceRecord` | Imported history from the Excel era: "tenant X attended N sessions of event E". `parts_count` holds the number of **sessions**, despite its name. |

## Who may do what

All management endpoints use `CheckedInView` and check `Event.admin_groups` per event
(`_is_event_admin`, ADMIN always passes). **Creating** an event needs Heimrat or
Netzwerkreferat. Listing events and scanning are open to every logged-in resident.

## The QR flow

1. An admin creates a session and starts a part (`sessions/<id>/start/` with `part`, or
   `toggle-status/`). This generates `secret_token`.
2. The projector page polls `sessions/<id>/current-token/`. The code is
   `"<session_id>_<token>"`. **The token rotates** whenever it is older than 30 seconds at
   poll time. The previous token stays valid for 15 seconds after a rotation, so a scan
   right at the switch still works.
3. The QR code holds a link into SmartDorm with that code. The resident scans it in the app
   (or opens the link and logs in), and the frontend posts it to `POST /api/attendance/scan/`.
4. The scan needs a `Tenant` for the logged-in account, an `ACTIVE` session and a valid token.
   It records the current part. Scanning twice is harmless.
5. `stop/` or `toggle-status/` closes the session and clears the token.

## Reports and corrections

- `sessions/<id>/report/`: a matrix of every tenant who hasn't moved out yet × the parts they
  attended, including manual overrides.
- `sessions/<id>/override/` with `tenant_id`, `part`, `present`: set or remove a record by hand
  (a dead phone, an exemption).
- `events/<id>/base-attendance/…`: per-tenant totals including the imported Excel history,
  and editing that history.
- `my-history/`: a resident's own records, with base attendance shown as one entry per event.
- A session with records can't be deleted. Clear its records first.
