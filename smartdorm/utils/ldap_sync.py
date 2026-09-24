"""
Shared rules for deriving LDAP group memberships from tenant/subtenant data.

Kept separate from `ldap_utils` (which is a model-free wrapper around python-ldap) so
that the views and the nightly `recalculate_tenant_stats` command apply exactly the same
rules instead of each holding their own copy.
"""

import logging

from django.utils import timezone

from smartdorm import config as app_config
from smartdorm.utils import ldap_utils

logger = logging.getLogger('smartdorm')

GROUPS2_BASE_DN = "ou=groups2,dc=schollheim,dc=net"

# employeeType stamped on accounts created by create_subtenant_view. Only these accounts
# are managed by the subtenant sync - see resolve_subtenant_username().
SUBTENANT_EMPLOYEE_TYPE = "SUBTENANT"


def floor_group_dn(floor):
    """DN of the LDAP group belonging to a floor, or None if no floor is set."""
    if not floor:
        return None
    return f"cn={floor},{GROUPS2_BASE_DN}"


def subtenant_floor(subtenant):
    """
    The floor a subtenant lives on.

    A subtenant sublets the main tenant's room, so the main tenant's denormalized
    current_floor is authoritative - it follows the tenant automatically when they move,
    unlike Subtenant.room which records the room at the time the sublet was registered.
    """
    return subtenant.tenant.current_floor if subtenant.tenant_id else None


def subtenant_target_group_dns(subtenant):
    """
    Lowercased set of group DNs a currently living subtenant should be a member of:
    the defaults plus their floor group.
    """
    target = {g.lower() for g in app_config.DEFAULT_SUBTENANT_LDAP_GROUPS}

    group_dn = floor_group_dn(subtenant_floor(subtenant))
    if group_dn:
        target.add(group_dn.lower())

    return target


def subtenant_managed_group_dns(all_floors):
    """
    Lowercased set of groups the sync is allowed to remove a subtenant from.

    Deliberately excludes the tenant-only groups ('cn=tenant', 'cn=Bewohner') so a
    subtenant account is never promoted to - or stripped of - a main tenant's roles.
    """
    managed = {g.lower() for g in app_config.DEFAULT_SUBTENANT_LDAP_GROUPS}

    for floor in all_floors:
        group_dn = floor_group_dn(floor)
        if group_dn:
            managed.add(group_dn.lower())

    return managed


def custom_role_dns_by_username():
    """
    {username_lower: {group_dn_lower, ...}} of every LdapRoleAssignment that is still
    valid today.

    Expired rows are left out so the sync stops treating them as owed - they are
    revoked separately by the nightly command.
    """
    from django.db.models import Q

    from smartdorm.models import LdapRoleAssignment

    today = timezone.now().date()
    assignments = LdapRoleAssignment.objects.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gte=today)
    )

    dns_by_username = {}
    for assignment in assignments:
        if not assignment.username or not assignment.group_dn:
            continue
        dns_by_username.setdefault(assignment.username.lower(), set()).add(assignment.group_dn.lower())

    return dns_by_username


def subtenant_base_username(name, surname):
    """
    The cn a subtenant account is created under, before any numeric suffix is appended.
    Deliberately a different format than tenant usernames ('j.doe') to avoid conflicts.
    """
    return (
        (name + " " + surname).lower().replace(' ', '')
        .replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    )


def find_subtenant_account(email, name, surname):
    """
    Resolves the LDAP cn of a person's existing subtenant account, or None.

    Subtenant has no username column, so the account is looked up:
    1. by email among SUBTENANT_EMPLOYEE_TYPE accounts - the normal case, and the only
       one that still works when the creation loop appended a numeric suffix.
    2. by the rebuilt name + surname cn, for accounts created before employeeType was
       stamped (those carry TENANT). Only accepted when the account's mail matches, so a
       namesake's account is never picked up.

    Subletting first and moving in later is common, so a subtenant's email very often
    also belongs to a tenant account - a main tenant's account is never returned.

    Raises ConnectionError when LDAP is unreachable, so an outage is never mistaken for
    a missing account.
    """
    from smartdorm.models import Tenant

    username = None
    if email:
        username, _ = ldap_utils.find_ldap_user_by_email(email, employee_type=SUBTENANT_EMPLOYEE_TYPE)

    if not username and email:
        candidate = subtenant_base_username(name or '', surname or '')
        mails = ldap_utils.get_ldap_user_emails(candidate) if candidate else None
        if mails and email.strip().lower() in {m.strip().lower() for m in mails}:
            username = candidate

    if username and Tenant.objects.filter(username__iexact=username).exists():
        logger.warning(
            f"LDAP account '{username}' found for subtenant '{email}' belongs to a "
            f"main tenant. Skipping to avoid modifying tenant groups."
        )
        return None

    return username


def resolve_subtenant_username(subtenant):
    """
    find_subtenant_account() for a Subtenant row, for callers that must not fail on an
    LDAP outage (floor-group follow-ups). Returns None when no account can be resolved.
    """
    try:
        username = find_subtenant_account(subtenant.email, subtenant.name, subtenant.surname)
    except ConnectionError as e:
        logger.error(f"Could not resolve LDAP user for subtenant '{subtenant.email}': {e}")
        return None

    if not username:
        logger.warning(f"No subtenant LDAP account found for '{subtenant.email}'.")

    return username


def apply_subtenant_floor_group(subtenant, old_floor, new_floor):
    """
    Moves a single subtenant from the old floor group to the new one.
    Returns True when the LDAP account could be resolved, False otherwise.
    """
    if old_floor == new_floor:
        return True

    username = resolve_subtenant_username(subtenant)
    if not username:
        return False

    old_group_dn = floor_group_dn(old_floor)
    if old_group_dn:
        ldap_utils.remove_user_from_group(username, old_group_dn)
        logger.info(f"Removed subtenant '{username}' from LDAP group for floor '{old_floor}'.")

    new_group_dn = floor_group_dn(new_floor)
    if new_group_dn:
        ldap_utils.add_user_to_group(username, new_group_dn)
        logger.info(f"Added subtenant '{username}' to LDAP group for floor '{new_floor}'.")

    return True


def sync_subtenant_floor_groups(tenant, old_floor, new_floor):
    """
    Follows a main tenant's floor change for all of their subtenants that have not
    moved out yet. Failures are logged per subtenant so one broken record cannot abort
    the tenant's move.
    """
    from smartdorm.models import Subtenant

    if old_floor == new_floor:
        return

    today = timezone.now().date()
    subtenants = Subtenant.objects.filter(tenant=tenant, move_out__gte=today).select_related('tenant')

    for subtenant in subtenants:
        try:
            apply_subtenant_floor_group(subtenant, old_floor, new_floor)
        except Exception as e:
            logger.error(
                f"Error updating LDAP floor group for subtenant '{subtenant.email}' "
                f"of tenant '{tenant.username}': {e}",
                exc_info=True
            )
