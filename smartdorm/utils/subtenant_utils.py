"""
Resolves a logged-in account back to the subtenant record it belongs to.

`t_subtenant` has no username column, so - exactly like `ldap_sync.resolve_subtenant_username()`
does in the other direction - the link between an authenticated user and their record
runs over the email address.
"""

import logging

from django.utils import timezone

from smartdorm.models import Subtenant, Tenant
from smartdorm.utils.ldap_sync import SUBTENANT_EMPLOYEE_TYPE

logger = logging.getLogger(__name__)


def get_current_subtenant(user):
    """
    The subtenant record of the currently running sublet for `user`, or None.

    A person can sublet more than once, so the email matches several rows over time.
    Only a sublet that has started and not yet ended counts, newest first - the same
    "current" definition the parcel views use.
    """
    if not user or not user.is_authenticated or not user.email:
        return None

    today = timezone.now().date()

    return (
        Subtenant.objects
        .filter(email__iexact=user.email, move_in__lte=today, move_out__gte=today)
        .select_related('tenant', 'room')
        .order_by('-move_in')
        .first()
    )


def is_subtenant_account(user):
    """
    Whether `user` logged in with a subtenant account.

    The employeeType stamped at creation is authoritative. Accounts created before that
    stamping was introduced carry employeeType TENANT, so they are recognised by the
    shape of their data instead: no tenant record for the username, but a running
    sublet on the email. A main tenant always has a `Tenant` row and therefore never
    falls into the fallback, even while they are also listed as a former subtenant.

    The result is cached on the user instance, which lives for exactly one request, so
    the fallback queries run at most once per request even though the middleware and the
    permission classes both ask.
    """
    if not user or not user.is_authenticated:
        return False

    cached = getattr(user, '_smartdorm_is_subtenant', None)
    if cached is not None:
        return cached

    if user.first_name == SUBTENANT_EMPLOYEE_TYPE:  # first_name holds employeeType
        result = True
    elif user.username and Tenant.objects.filter(username=user.username).exists():
        result = False
    else:
        result = get_current_subtenant(user) is not None

    user._smartdorm_is_subtenant = result
    return result
