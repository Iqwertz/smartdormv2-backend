# Authentication & Permissions

## Authentication

The SmartDorm backend uses a combination of LDAP for user identity and Django's session framework for authenticating API requests.

### LDAP Integration

*   **Primary Source of Truth**: The central LDAP server (`ldap.schollheim.net`; development and test systems use `ldap-test.schollheim.net`) is the single source of truth for users and their group memberships.
*   **Mechanism**: The `django-auth-ldap` library is used. When a user logs in via `POST /api/auth/login/`, Django's `authenticate()` function delegates the credential check to the LDAP backend.
*   **User Model Sync**: On successful authentication, `django-auth-ldap` populates the Django `User` model with attributes from the LDAP directory. The mapping is defined in `settings.py`:
    ```python
    # smartdorm/settings.py
    AUTH_LDAP_USER_ATTR_MAP = {
        "first_name": "employeeType", # CRITICAL: We use first_name to store the user type.
        "last_name": "sn",
        "email": "mail",
    }
    ```
*   **User Type (`employeeType`)**: A crucial detail is that the LDAP `employeeType` attribute (e.g., 'TENANT', 'DEPARTMENT') is mapped to the Django `user.first_name` field. Access rules do not use it (see Permissions); it is used to recognise subtenant accounts.
*   **Group Sync**: At login, the user's LDAP groups (from `ou=groups`, `ou=roles` and `ou=groups2`) are copied by name (`cn`) onto the Django user (`AUTH_LDAP_MIRROR_GROUPS`). Both the access rules and the frontend (via `GET /api/auth/me/`) read this copy. It is only refreshed at login, and sessions last up to two weeks: **a group change in LDAP takes effect at the user's next login.**

### Session Management

*   **Mechanism**: The backend uses Django's standard session authentication (`rest_framework.authentication.SessionAuthentication`).
*   **Storage**: User sessions are stored in **Redis**, not the database. This is configured in `settings.py` and provides better performance.
*   **Credentials**: The frontend must send the `sessionid` cookie with every authenticated request. CORS is configured to allow this (`CORS_ALLOW_CREDENTIALS = True`).

## Permissions

Who may call which endpoint is decided in **one file**, `smartdorm/permissions.py`, and
declared on each view with **one line**. A startup check makes sure no endpoint is left
without a declaration.

### How a request is checked

1. **Authentication**: DRF's `SessionAuthentication` identifies the user from the session
   cookie.
2. **Subtenant guard**: `SubtenantApiGuardMiddleware` turns away subtenant accounts from
   everything except `/api/auth/` and `/api/subtenant/` (see *Subtenant Accounts*).
3. **The view's access rule**: the one rule in the view's `@permission_classes` decides.
   Refusals give 403, and group rules log who was refused where (see *Troubleshooting a 403*).
4. **Per-object check**, only for `CheckedInView` views: the view itself checks the groups
   that belong to the object, such as an event's admin groups or a signature's department.

### Where things live

| File | Purpose |
|---|---|
| `smartdorm/permissions.py` | group names (`Groups`), all access rules, `user_in_groups()` |
| `smartdorm/checks.py` | startup check `smartdorm.E001`: every API view declares exactly one rule |
| `smartdorm/access_inventory.py` | walks all API endpoints; shared by the check, the command and the tests |
| `smartdorm/management/commands/list_api_access.py` | `manage.py list_api_access`: who may call what |
| `smartdorm/middleware.py` | `SubtenantApiGuardMiddleware` |
| `smartdorm/tests/test_access.py`, `tests/api_access.txt` | access tests and the reviewed snapshot |

### The rules in short

1. **Every API view declares exactly one access rule** in `@permission_classes`, and
   nothing else:

    ```python
    from ..permissions import IsVerwaltung

    @api_view(['GET'])
    @authentication_classes([SessionAuthentication])
    @permission_classes([IsVerwaltung])
    def all_tenant_data_view(request):
        ...
    ```

2. **Access is based on LDAP groups, not on `employeeType`.** The frontend guards its routes
   and tabs by groups only, and the people who need the admin pages don't share one
   employeeType: ADMIN members are `TENANT` accounts, while the Verwaltung account is
   `DEPARTMENT`. A backend check on employeeType would lock out people the frontend lets in.
3. **ADMIN is always allowed** by every group rule, so it's never listed.
4. **Rules are named after the audience or feature they guard** (`IsVerwaltung`,
   `CanViewResidentStatistics`), not after a list of groups. To change who may use a
   feature, edit that rule's `groups`; every endpoint of the feature follows.
5. **Subtenants are handled centrally** by `SubtenantApiGuardMiddleware` (see below). No rule
   needs to exclude them.

### The available rules

| Rule | Who gets in | Use for |
|---|---|---|
| `Public` | anyone, no login | login, password reset, the Pi scan monitor |
| `LoggedIn` | any logged-in account | self-service endpoints that only touch the caller's own data (`Tenant.objects.get(username=request.user.username)`), and data every resident may see |
| `CheckedInView` | logged in; **the view decides per object** | cases where the right groups depend on the object (attendance events, departure signatures). The view must call `user_in_groups()` |
| `IsSubtenant` | subtenant accounts | the subtenant dashboard |
| `HasDeviceToken` | the Pi print agent (shared token) | `/api/printing/agent/*` |
| `IsVerwaltung` | VERWALTUNG | tenants, subtenants, departures, claims, extensions, parcels, printer admin, tenant/room pickers |
| `IsHeimrat` | Heimrat | Heimrat page: applications, semester switch with LDAP sync |
| `IsSemesterManager` | Heimrat, Netzwerkreferat | global semester and application switches |
| `IsEngagementManager` | Heimrat, Inforeferat | Referate page |
| `IsNetworkAdmin` | Netzwerkreferat | Netzwerkreferat page: departments, LDAP roles, logs |
| `CanViewResidentOverview` | Heimrat, Info-, Zimmer-, Finanzen-, Schlichtungsreferat | Bewohnerübersicht: overview, Referate overview, CSV download |
| `CanViewResidentEngagements` | the above + HSV-Vertreter | resident engagement table (overview and HSV tabs) |
| `CanViewResidentStatistics` | Heimrat, Info-, Zimmer-, Finanzenreferat, HSV-Vertreter | statistics tab |

ADMIN is additionally allowed by every group rule. `python manage.py list_api_access` prints
the live version of this table for every endpoint (`--rule IsVerwaltung` filters by rule).

### Common tasks

**Adding an endpoint.** Pick the rule from the table and put it in `@permission_classes`. If
the endpoint belongs to an existing page, use that page's rule. Then update the snapshot (see
*Tests* below).

**Changing who may use a feature.** Edit the `groups` of its rule in `permissions.py`, then
update the matching `requiredGroups` / `authGroups` in the frontend
(`smartdormv2-frontend/src/routesConfig.tsx` and the tabbed pages). The backend decides
access; the frontend only hides what the user couldn't use anyway. If the two disagree,
users see buttons that fail with 403, or lose access they should have. Update the snapshot
too.

**Adding a new audience.** Add a rule class next to the others:

```python
class CanManageParcels(GroupRule):
    """Parcel desk: Verwaltung and the Pfortenreferat."""

    groups = (Groups.VERWALTUNG, Groups.PFORTENREFERAT)
```

Add new group names to `Groups` first. They must match the LDAP `cn` exactly, including
case: `VERWALTUNG` and `Verwaltung` are two different groups, and only the first one has the
Verwaltung account in it.

**Per-object checks.** Declare `CheckedInView` and check inside the view before touching the
object:

```python
if not user_in_groups(request.user, [config["group"]]):
    return Response({"detail": "..."}, status=status.HTTP_403_FORBIDDEN)
```

### What not to do, and why

**Never attach requirements to the view function** (`my_view.required_groups = [...]`).
`@api_view` turns the function into a generated `APIView` class and copies over only a few
known attributes, such as `permission_classes`. Anything else set on the function never
reaches a permission class. Until September 2026 the whole backend used that pattern.
Its permission class read an empty list, treated "no requirement" as "everyone", and so
nearly every endpoint was open to every logged-in resident. That included all tenant data,
deleting tenants, and resetting other accounts' LDAP passwords.

These safeguards keep that from happening again:

* **Startup check** (`smartdorm/checks.py`, id `smartdorm.E001`). Django runs it before
  `runserver`, `migrate` and `manage.py check`, and `deploy.sh` runs `migrate`. An `/api/`
  view that declares no rule, more than one rule, or a plain DRF class such as
  `IsAuthenticated` stops the server from starting and aborts the deploy before gunicorn
  restarts. The error names the view and explains the fix.
* **No "empty means everyone"**: a `GroupRule` subclass without groups raises at import.
* **One way to do it**: the old `GroupAndEmployeeTypePermission`, `HasGroupPermission` and
  `HasUserTypePermission` are gone, so there is nothing left to copy the old pattern from.
* **Tests** (see below): they fail if a rule starts letting in the wrong people, and whenever
  access changes without the reviewed snapshot being updated.

### Tests

`smartdorm/tests/test_access.py` runs in well under a second and needs no database, because
permissions are decided before a view touches any data:

```bash
python manage.py test smartdorm.tests.test_access   # also the first step of ./run-tests.sh
```

It covers:

* **The rules themselves**, using fake users: members and ADMIN get in, everyone else is
  refused, and the device token and subtenant checks behave correctly.
* **The real API, through DRF's own permission check**, for typical accounts. Anonymous users
  reach only `Public` endpoints, and a tenant with no roles reaches no group endpoint. The
  Verwaltung account reaches the Verwaltung area, and ADMIN reaches everything, even though
  ADMIN members are `TENANT` accounts.
* **The per-object checks** (signatures, attendance events) and the read-only `username`.
* **The startup check**: it must flag views that use the old style, declare no rule, or
  declare two rules.
* **The access snapshot**. `smartdorm/tests/api_access.txt` lists every endpoint grouped under
  the rule that guards it, with the groups that rule lets in. If the code no longer matches
  it, the test fails and prints the difference. When the change is intended, regenerate it:

    ```bash
    python manage.py list_api_access --write-snapshot
    ```

  Commit the snapshot with the change. Its diff shows the reviewer who gained or lost
  access to what, even when only a group list inside `permissions.py` changed.

### Troubleshooting a 403

* **The log says who and why.** Every refusal by a group rule is logged:
  `Access denied by IsVerwaltung: 'jdoe' is not in VERWALTUNG, ADMIN (/api/department/tenant-data/).`
  Search for it with `grep "Access denied by" logs/smartdorm.log`.
* **The user should have the group:** check the membership in LDAP, then have them log out and
  back in. Groups are copied from LDAP only at login.
* **The group should not be enough, or should be:** that is a rule change (see *Common tasks*).
  Check the frontend's group lists too.
* **No "Access denied" line:** the refusal came from elsewhere. It could be the subtenant guard
  (`Blocked subtenant ...`), a per-object check inside a `CheckedInView` view, or Django's
  CSRF protection on POST/PUT/DELETE (see the deployment guide).

### Related hardening

* `TenantSerializer` treats `username` as read-only. The username names the tenant's LDAP
  account; if it were writable, an edit could point the record, and with it a credential
  resend, at another account.
* The Pi print agent's endpoints check the shared `DEVICE_AGENT_TOKEN` through the
  `HasDeviceToken` rule. They answer `401 {"error": "Unauthorized."}` without it, and refuse
  everything while no token is configured.
* **Open:** the Pi scan monitor's `GET /api/printing/active-session/` and
  `POST /api/printing/scans/` are still `Public`, because the scan service does not send a token
  yet. Securing them needs a change on the Pi.

### Subtenant Accounts

Subtenants (`Untermieter`) get an LDAP account so they can use the wlan and the wiki, but
they are not residents and must not see resident data.

*   **Marking**: `create_subtenant_view` stamps their LDAP account with `employeeType=SUBTENANT`
    and adds them only to the groups in `config.DEFAULT_SUBTENANT_LDAP_GROUPS` (`wlan`, `wiki`)
    plus their floor group. They never get the `tenant` role.
*   **Recognising them**: `utils/subtenant_utils.is_subtenant_account()`. Accounts created
    before the `employeeType` stamping was introduced (October 2025) carry `TENANT`, so the
    helper falls back to the shape of the data: no `Tenant` row for the username, but a
    running sublet on the email address. `GET /api/auth/me/` exposes the result as
    `is_subtenant`, which is what the frontend routes on.
*   **Their own record**: `t_subtenant` has no username column, so a logged-in subtenant is
    matched to their record by **email**, restricted to the sublet that is currently running
    (`utils/subtenant_utils.get_current_subtenant()`).

#### Enforcement: `SubtenantApiGuardMiddleware`

Subtenants are logged-in accounts, so every `LoggedIn` endpoint would admit them, and older
subtenant accounts even carry the `TENANT` employeeType. Instead of excluding them rule by
rule, `smartdorm/middleware.py` denies subtenant accounts **every** path under `/api/` that is
not listed in `config.SUBTENANT_ALLOWED_API_PREFIXES`:

```python
SUBTENANT_ALLOWED_API_PREFIXES = [
    '/api/auth/',       # session handling and the user's own password
    '/api/subtenant/',  # the subtenant dashboard's own data
]
```

This is default-deny: **an endpoint added later is closed to subtenants until someone opens
it deliberately.** The subtenant dashboard's own endpoints declare the `IsSubtenant` rule.
