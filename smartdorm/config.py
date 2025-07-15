# Application specific settings for SmartDorm

# --- Tenant Creation Settings ---
PROBATION_PERIOD_DAYS = 180
DEFAULT_CONTRACT_DURATION_DAYS = 365

# --- LDAP Settings ---
# List of DNs for groups to which new tenants are automatically added.
DEFAULT_TENANT_LDAP_GROUPS = [
    'cn=tenant,ou=roles,dc=schollheim,dc=net',
]

# List of DNs for groups to which new subtenants are automatically added.
DEFAULT_SUBTENANT_LDAP_GROUPS = [
    'cn=tenant,ou=roles,dc=schollheim,dc=net', # Just for testing
]