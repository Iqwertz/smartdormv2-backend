# Application specific settings for SmartDorm

#-- Email Settings ---
DEPARTMENT_EMAIL = 'verwaltung@schollheim.net'

#-- Departure Settings --
DEPARTURE_SIGNATURE_ENGAGEMENTS = ["TUTOREN", "BAR", "WERK", "INNEN", "FINANZEN"]

# --- Tenant Creation Settings ---
PROBATION_PERIOD_DAYS = 365
DEFAULT_CONTRACT_DURATION_DAYS = 365 * 3 
DEFAULT_EXTENSION_DURATION_DAYS = 365

# --- LDAP Settings ---
# List of DNs for groups to which new tenants are automatically added.
DEFAULT_TENANT_LDAP_GROUPS = [
    'cn=tenant,ou=roles,dc=schollheim,dc=net',
    'cn=wlan,ou=groups,dc=schollheim,dc=net',
    'cn=wiki,ou=groups,dc=schollheim,dc=net', 
    'cn=Bewohner,ou=groups2,dc=schollheim,dc=net'
]

# List of DNs for groups to which new subtenants are automatically added.
DEFAULT_SUBTENANT_LDAP_GROUPS = [
    'cn=wlan,ou=groups,dc=schollheim,dc=net',
    'cn=wiki,ou=groups,dc=schollheim,dc=net', 
]

# --- Subtenant Access Settings ---
# Subtenants hold an account for the wlan and the wiki and have no business with the
# rest of SmartDorm, so SubtenantApiGuardMiddleware denies them every API path that is
# not listed here. Default-deny on purpose: an endpoint added later is closed to
# subtenants until someone opens it deliberately.
SUBTENANT_ALLOWED_API_PREFIXES = [
    '/api/auth/',       # session handling and the user's own password
    '/api/subtenant/',  # the subtenant dashboard's own data
]
