# Application specific settings for SmartDorm

# --- Tenant Creation Settings ---
PROBATION_PERIOD_DAYS = 180
DEFAULT_CONTRACT_DURATION_DAYS = 365

# --- Move Out Settings ---
DEPARTURE_CANDIDATE_TIMEFRAME_DAYS = 30
DEPARTURE_SIGNATURE_DEPARTMENTS = [
    'Tutoren',
    'Barreferat',
    'Werkreferat',
    'Innenreferat',
    'Finanzenreferat'
]

# --- LDAP Settings ---
# List of DNs for groups to which new tenants are automatically added.
DEFAULT_TENANT_LDAP_GROUPS = [
    'cn=tenant,ou=roles,dc=schollheim,dc=net',
]

# List of DNs for groups to which new subtenants are automatically added.
DEFAULT_SUBTENANT_LDAP_GROUPS = [
    'cn=wlan,ou=groups,dc=schollheim,dc=net',
]