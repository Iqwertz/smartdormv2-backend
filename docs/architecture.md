# Architecture

## Overview

```text
Browser (React SPA, smartdormv2-frontend)
   │  JSON over HTTPS, session cookie + CSRF token (cookies on .schollheim.net)
   ▼
Nginx → Gunicorn → Django / DRF  ──────────────►  PostgreSQL   legacy t_* tables + Django tables
                    │   │   │
                    │   │   └──────────────────►  LDAP         accounts, passwords, groups
                    │   └──────────────────────►  Redis        sessions, PDF + image caches
                    └──────────────────────────►  SMTP         noreply@schollheim.net
Raspberry Pi print agent ──polls──► /api/printing/agent/*   (docs/features/printing.md)
cron 04:00 ──► manage.py recalculate_tenant_stats           (docs/ldap.md)
```

A request goes through CORS → sessions → CSRF → authentication → `SubtenantApiGuardMiddleware`
→ the view's single access rule → the view. The view does its own per-object checks when its
rule is `CheckedInView`. See [permissions.md](permissions.md).

## Code layout

| Path | What's in it |
| --- | --- |
| `smartdorm/settings.py` | Django settings, everything environment-specific comes from env vars |
| `smartdorm/config.py` | domain constants: contract lengths, default LDAP groups, signature Referate, subtenant API allow-list |
| `smartdorm/models.py` | all models |
| `smartdorm/serializers.py` | DRF serializers (input validation and output shapes) |
| `smartdorm/urls.py` | all routes, grouped by area |
| `smartdorm/views/auth_views.py` | login, logout, `me`, password reset/change, dev account list |
| `smartdorm/views/tenant_views.py` | resident self-service (`/api/tenants/`) |
| `smartdorm/views/department_views.py` | Verwaltung: tenants, moves, subtenants, departures, signatures, claims, terminations, extensions |
| `smartdorm/views/engagement_views.py` | Heimrat/Inforeferat/Netzwerkreferat: applications, engagements, semester, Referate list, overviews, CSV |
| `smartdorm/views/parcel_views.py`, `shared_views.py`, `network_views.py`, `log_views.py`, `subtenant_views.py` | parcels, dropdown data, manual LDAP roles, log viewer, subtenant dashboard |
| `smartdorm/views/attendance_views.py`, `printing_views.py` | features, see `docs/features/` |
| `smartdorm/utils/helper.py` | semester helpers, contract dates, departure signatures |
| `smartdorm/utils/ldap_utils.py` | model-free python-ldap wrapper (create, password, groups, lookups) |
| `smartdorm/utils/ldap_sync.py` | rules for which groups an account should have (shared by views and the nightly job) |
| `smartdorm/utils/email_utils.py`, `pdf_utils.py`, `credential_utils.py`, `subtenant_utils.py`, `log_utils.py`, `cups_utils.py` | mail, PDF forms, password resend, subtenant lookup, log file, legacy CUPS |
| `smartdorm/permissions.py`, `checks.py`, `access_inventory.py`, `middleware.py` | access control |
| `smartdorm/templates/email/` | mail templates, all based on `template.html` |
| `smartdorm/templates/pdf/` | PDF forms filled with pypdf (Wohnzeitende-Mitteilung, extension application, departure) |

**API areas:** `/api/auth/`, `/api/tenants/` (resident), `/api/subtenant/`,
`/api/department/` (Verwaltung), `/api/engagements/`, `/api/common/` (dropdowns),
`/api/network/`, `/api/attendance/`, `/api/printing/`. The complete, current list of endpoints
and who may call them is `manage.py list_api_access` (also committed as
`smartdorm/tests/api_access.txt`).

## Conventions in the code

- Views are functions: `@api_view`, `@authentication_classes([SessionAuthentication])`,
  `@permission_classes([<one rule>])`, and `@transaction.atomic` when they write.
- Errors come back as `{"error": "..."}` with a fitting status. Success bodies are serializer
  data or `{"message": ...}`.
- "Current" tenants are `move_in <= today <= move_out`. The same filter appears in many views.
- The logged-in resident's record is `Tenant.objects.get(username=request.user.username)`.
- Mails: `email_utils.send_email_message(recipient_list, subject, html_template_name, context,
  …)`. It can attach a filled PDF form. It returns `False` instead of raising, so check the
  result. **Outside production every mail goes to `DEVELOPER_EMAIL`.**
- Log with the module logger (`logging.getLogger(__name__)`). Everything goes to
  `logs/smartdorm.log`, which the Netzwerkreferat can read in the frontend.

## The database

Two kinds of tables share one Postgres database:

- **Legacy tables** (`t_tenant`, `t_room`, `t_rental`, `t_department`, `t_engagement`,
  `t_engagement_application`, `t_departure`, `t_department_signature`, `t_parcel`,
  `t_subtenant`, `t_claim`, `t_deposit_bank`, `t_user`, `offline_user*`) come from SmartDorm
  v1. v1 is shut down, but the tables and their data stay. The models are `managed = False`:
  Django reads and writes them but never changes their schema on its own.
- **Django tables** (`managed = True`): `GlobalAppSettings`, `Termination`,
  `DepartmentExtension`, `LdapRoleAssignment`, the attendance models and the printing models.
  Normal migrations.

Things to know about the legacy tables:

- **No auto-increment ids.** New rows get `id = max(id) + 1`, computed in the view, plus
  `external_id = uuid4().hex`. Copy that pattern (see `create_new_tenant_view`). It can
  collide under concurrent writes (tracked in [todo.md](todo.md)).
- Denormalized fields on `Tenant` (`current_room`, `current_floor`, `current_points`,
  `extension`, `sublet`) must be kept in step by whoever changes the source data. The nightly
  job repairs points, sublet and extension.
- `Subtenant.move_in` maps to the DB column `move_id` (v1 typo).
- `t_user` and `offline_user*` are v1 leftovers that nothing uses.

### Changing the database

**Rule: prefer columns over tables.**

- If the new data belongs to one existing thing (a tenant's X, a room's Y, a global
  switch), **add a column** to that thing's table. Global switches go on `GlobalAppSettings`.
- **Create a table** only for a new thing that exists many times per parent and has its own
  life: print jobs, attendance records, Verwaltung extensions, role assignments. Squeezing
  those into columns or JSON is worse than a table.
- In hindsight, `Termination` (one per tenant) would have been two columns on `t_tenant`.
  Leave it as it is; moving it isn't worth the churn.

**Adding a column to a legacy table.** Because the model is `managed = False`, `makemigrations`
ignores the new field (verified). Write the migration by hand:

```python
# smartdorm/migrations/00xx_tenant_parking_spot.py
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("smartdorm", "00xx_previous")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE t_tenant ADD COLUMN IF NOT EXISTS parking_spot varchar(20) NULL;",
                    reverse_sql="ALTER TABLE t_tenant DROP COLUMN IF EXISTS parking_spot;",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="tenant",
                    name="parking_spot",
                    field=models.CharField(max_length=20, null=True, blank=True),
                ),
            ],
        ),
    ]
```

Then add the same field to the model.

**Legacy rows don't have the new data.** Decide for every new column:

- **Nullable** when "unknown" is a real state. Old rows stay `NULL`.
- **`NOT NULL` with a SQL default** (`ADD COLUMN … NOT NULL DEFAULT false`) when there is a
  correct value for old rows. Postgres fills it in. Django 4.2's `default=` does **not** do
  this; it only applies to rows created from Python.
- **Backfill** with a `RunPython` step when the value can be derived from existing data.
- Handle `NULL` in **one place**, such as a model property or helper, not in every view.

**Never** rename, drop or change the type of a legacy column. Only add.

Migrations run on deploy (`deploy.sh` → `migrate`), on the test server first. Run them
locally only with `.env` sourced and `DB_HOST` checked (see [development.md](development.md)).

## LDAP and the database together

Most writes touch both. LDAP has no transactions, so:

1. Validate and resolve everything first. Look up accounts **before** overwriting the values
   used to find them (e.g. a subtenant's old email).
2. Write the DB rows inside `transaction.atomic()`.
3. Do the LDAP writes **last**. If they fail, roll the rows back
   (`transaction.set_rollback(True)`) and return an error.
4. If an LDAP step is only a follow-up (a floor group after a move), log the failure and let
   the nightly sync repair it.

Details on accounts and groups: [ldap.md](ldap.md).

## Caching

Redis (`CACHES["default"]`) holds sessions, the applications PDF per semester
(`applications_pdf_<semester>`, plus a lock key), and application photos
(`appimg:<id>`). Clearing Redis logs everyone out.
