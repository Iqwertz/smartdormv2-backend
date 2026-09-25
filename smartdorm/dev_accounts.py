"""
Dev accounts: one LDAP account per role, for trying SmartDorm the way each group sees it.

They are real accounts in the *test* LDAP, so logging in with one runs the same path as a
real person - LDAP bind, group mirroring, employeeType. `manage.py dev_accounts` creates,
refreshes and deletes them; the login page lists them when SHOW_DEV_ACCOUNTS is set.

Resident accounts also get a tenant record with obviously fake data, so the resident pages
(profile, points, printing, ...) have something to show. They appear in Verwaltung's lists
as "DEV-Testkonto dev-...".

There is one account per group in permissions.Groups, so a group added there gets its dev
account the next time the command runs.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlparse

from .permissions import Groups

TENANT_ROLE = "tenant"  # cn=tenant,ou=roles - what makes the frontend show the resident pages
EMAIL_DOMAIN = "smartdorm-dev.invalid"  # marks LDAP accounts and tenant records as dev data
DUMMY_NAME = "DEV-Testkonto"

# The only places dev accounts may be written to, whatever PRODUCTION says. Add a host here
# only if it is certainly not production.
TEST_LDAP_HOSTS = {"ldap-test.schollheim.net"}
TEST_DATABASE_HOSTS = {"db-test-smartdorm-v2.schollheim.net", "localhost", "127.0.0.1"}


def non_test_targets(ldap_uri, database_host):
    """What in the given configuration is not a known test system - empty if it is safe."""
    problems = []
    ldap_host = urlparse(ldap_uri or "").hostname
    if ldap_host not in TEST_LDAP_HOSTS:
        problems.append(f"LDAP host '{ldap_host}' is not a test LDAP ({', '.join(sorted(TEST_LDAP_HOSTS))})")
    if (database_host or "").lower() not in TEST_DATABASE_HOSTS:
        problems.append(f"database host '{database_host}' is not a test database ({', '.join(sorted(TEST_DATABASE_HOSTS))})")
    return problems


@dataclass(frozen=True)
class DevAccount:
    username: str
    employee_type: str
    groups: tuple
    description: str

    @property
    def email(self):
        return f"{self.username}@{EMAIL_DOMAIN}"

    @property
    def has_tenant_record(self):
        return self.employee_type == "TENANT"

    def dummy_tenant_fields(self, today):
        """A resident living here right now, with values nobody could take for real data."""
        return {
            "name": DUMMY_NAME,
            "surname": self.username,
            "email": self.email,
            "birthday": date(2000, 1, 1),
            "gender": "UNBEKANNT",
            "nationality": "Testdaten",
            "university": "Testdaten",
            "study_field": "Testdaten",
            "current_room": "DEV-000",
            "current_floor": "DEV",
            "move_in": today - timedelta(days=180),
            "move_out": today + timedelta(days=730),
            "probation_end": today + timedelta(days=185),
            "current_points": Decimal("0"),
            "deposit": Decimal("0"),
            "extension": 0,
            "sublet": 0,
            "note": "Testkonto aus manage.py dev_accounts - keine echte Person.",
        }


def _one_per_role_group():
    special = {Groups.ADMIN, Groups.VERWALTUNG}
    for name, group in vars(Groups).items():
        if name.isupper() and group not in special:
            yield DevAccount(f"dev-{group.lower()}", "TENANT", (TENANT_ROLE, group), f"Bewohner mit Rolle {group}")


DEV_ACCOUNTS = (
    DevAccount("dev-bewohner", "TENANT", (TENANT_ROLE,), "Bewohner ohne Rolle"),
    DevAccount("dev-admin", "TENANT", (TENANT_ROLE, Groups.ADMIN), "ADMIN (Bewohnerkonto, wie in echt)"),
    DevAccount("dev-verwaltung", "DEPARTMENT", (Groups.VERWALTUNG,), "Verwaltungskonto"),
    *_one_per_role_group(),
    # Signature pages check their department's group inside the view (CheckedInView).
    DevAccount("dev-barreferat", "TENANT", (TENANT_ROLE, "Barreferat"), "Bewohner im Barreferat (Unterschriften)"),
    DevAccount("dev-untermieter", "SUBTENANT", (), "Untermieter"),
)
