# Application specific settings for SmartDorm

# --- Tenant Creation Settings ---
PROBATION_PERIOD_DAYS = 180
DEFAULT_CONTRACT_DURATION_DAYS = 365

# --- LDAP Settings ---
# List of Distinguished Names (DNs) for groups to which new tenants are automatically added.
DEFAULT_TENANT_LDAP_GROUPS = [
    'cn=tenant,ou=roles,dc=schollheim,dc=net',
]