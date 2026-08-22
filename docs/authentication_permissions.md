# Authentication & Permissions

## Authentication

The SmartDorm backend uses a combination of LDAP for user identity and Django's session framework for authenticating API requests.

### LDAP Integration

*   **Primary Source of Truth**: The central LDAP server (`ldap.schollheim.net`) is the single source of truth for users and their group memberships.
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
*   **User Type (`employeeType`)**: A crucial detail is that the LDAP `employeeType` attribute (e.g., 'TENANT', 'DEPARTMENT') is mapped to the Django `user.first_name` field. This is used extensively in permission checks.
*   **Group Sync**: User groups are also synchronized from LDAP and mirrored as Django `Group` objects.

### Session Management

*   **Mechanism**: The backend uses Django's standard session authentication (`rest_framework.authentication.SessionAuthentication`).
*   **Storage**: User sessions are stored in **Redis**, not the database. This is configured in `settings.py` and provides better performance.
*   **Credentials**: The frontend must send the `sessionid` cookie with every authenticated request. CORS is configured to allow this (`CORS_ALLOW_CREDENTIALS = True`).

## Permissions

Access to API endpoints is controlled by a custom permission class that checks both group membership and user type.

*   **Custom Class**: `GroupAndEmployeeTypePermission` located in `smartdorm/permissions.py`.
*   **Usage**: Views apply this permission and define their specific requirements as attributes.

#### 1. Group Check (`required_groups`)

Views can specify a list of LDAP groups that are allowed to access them.

*   **Example**:
    ```python
    # smartdorm/views/department_views.py
    @api_view(['GET'])
    @permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
    def all_tenant_data_view(request):
        all_tenant_data_view.required_groups = ['VERWALTUNG', 'ADMIN']
        # ... view logic ...
    ```
*   **Logic**: The permission class checks if the authenticated user belongs to *any* of the groups in the `required_groups` list.

#### 2. User Type Check (`required_employee_types`)

Views can also restrict access based on the user's `employeeType` from LDAP (which is stored in `user.first_name`).

*   **Example**:
    ```python
    # smartdorm/views/tenant_views.py
    @api_view(['GET'])
    @permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
    def profile_data_view(request):
        profile_data_view.required_employee_types = ['TENANT']
        # ... view logic ...
    ```
*   **Logic**: The permission class checks if the user's `employeeType` is present in the `required_employee_types` list.

### 3. Subtenant Accounts

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

Because `required_groups` / `required_employee_types` are silently ignored on `@api_view`
endpoints (see above), most endpoints currently resolve to "any authenticated user" - which
would include subtenants. Rather than relying on ~100 individual declarations,
`smartdorm/middleware.py` denies subtenant accounts **every** path under `/api/` that is not
listed in `config.SUBTENANT_ALLOWED_API_PREFIXES`:

```python
SUBTENANT_ALLOWED_API_PREFIXES = [
    '/api/auth/',       # session handling and the user's own password
    '/api/subtenant/',  # the subtenant dashboard's own data
]
```

This is default-deny: **an endpoint added later is closed to subtenants until someone opens
it deliberately.** The `IsSubtenant` / `IsNotSubtenant` permission classes in `permissions.py`
are available for view-level checks on top of that.

By combining these two checks, the system provides granular control over who can access what data and perform which actions.