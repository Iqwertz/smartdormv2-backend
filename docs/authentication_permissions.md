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

By combining these two checks, the system provides granular control over who can access what data and perform which actions.