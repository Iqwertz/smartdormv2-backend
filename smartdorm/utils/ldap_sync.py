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


def resolve_subtenant_username(subtenant):
    """
    Resolves a subtenant's LDAP cn.

    Subtenant has no username column, and rebuilding it from name + surname breaks as
    soon as the creation loop appended a numeric suffix, so we look the account up by
    its email address instead.

    The lookup is restricted to SUBTENANT_EMPLOYEE_TYPE accounts: subletting first and
    moving in later is common, so a subtenant's email very often also belongs to a
    tenant account that this sync must never touch. Returns None when no subtenant
    account exists.
    """
    from smartdorm.models import Tenant

    if not subtenant.email:
        return None

    try:
        username, _ = ldap_utils.find_ldap_user_by_email(
            subtenant.email, employee_type=SUBTENANT_EMPLOYEE_TYPE
        )
    except ConnectionError as e:
        logger.error(f"Could not resolve LDAP user for subtenant '{subtenant.email}': {e}")
        return None

    if not username:
        logger.warning(f"No subtenant LDAP account found for '{subtenant.email}'.")
        return None

    if Tenant.objects.filter(username=username).exists():
        logger.warning(
            f"LDAP account '{username}' found for subtenant '{subtenant.email}' belongs to a "
            f"main tenant. Skipping to avoid modifying tenant groups."
        )
        return None

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
