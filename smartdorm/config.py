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

# --- HSV e.V. membership settings ---
# The HSV e.V. is a separate legal entity from the Schollheim e.V. whose tenancy data makes up
# the rest of this system. Everything below concerns the Verein, not the Wohnheim.

# Groups whose holders may approve or deny a Beitrittsantrag and see the member register.
# Names are LDAP group cns, which are derived from Department.full_name - note it really is
# "Finanzenreferat", not "Finanzreferat".
MEMBERSHIP_APPROVER_GROUPS = ['Zimmerreferat', 'Finanzenreferat', 'Heimrat', 'ADMIN']

# Narrower gate for the SEPA collection file: only the Finanzenreferat submits to the bank.
MEMBERSHIP_FINANCE_GROUPS = ['Finanzenreferat', 'ADMIN']

# Mailbox that is notified when a new Beitrittsantrag comes in.
MEMBERSHIP_EMAIL = 'heimrat@schollheim.net'

# --- SEPA creditor identity ---
# TODO(legal): replace with the real Gläubiger-Identifikationsnummer issued by the Bundesbank.
# Until this is filled in, generating a collection file is refused - see docs/membership_legal.md.
HSV_CREDITOR_ID = 'DE00ZZZ00000000000'
HSV_CREDITOR_NAME = 'Studierendenwohnheim Geschwister Scholl Heimselbstverwaltung e.V.'
HSV_CREDITOR_ADDRESS = 'Steinickeweg 7, 80798 München'
# TODO(legal): the account the Mitgliedsbeiträge are collected into.
HSV_CREDITOR_IBAN = ''
HSV_CREDITOR_BIC = ''

# Monthly Mitgliedsbeitrag in EUR, as named in the Beitrittserklärung.
HSV_MEMBERSHIP_FEE_EUR = '10.00'

# Bank working day of the month the Beitrag is collected on. Appears in the mandate text as
# part of the shortened pre-notification agreement.
HSV_COLLECTION_DAY = 1

# Days before the due date the Vorabankündigung is sent. The SEPA default is 14 calendar days;
# a shorter period is only allowed because the mandate text agrees it explicitly.
HSV_PRENOTIFICATION_DAYS = 5

# A SEPA mandate that has not been used for this many months expires and must be re-obtained.
SEPA_MANDATE_EXPIRY_MONTHS = 36

# TODO(legal): public URLs for the documents the Beitrittserklärung references.
HSV_PRIVACY_POLICY_URL = ''
HSV_STATUTES_URL = ''
