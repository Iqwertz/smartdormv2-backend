"""
Access control for the SmartDorm API - the one place that decides who may call what.

Every API view declares exactly one *access rule* from this module, and nothing else:

    @api_view(['GET'])
    @permission_classes([IsVerwaltung])
    def all_tenant_data_view(request):
        ...

The startup check in `checks.py` refuses to run the server (and blocks `migrate`, and with
it the deploy) when an /api/ view declares no rule, several rules, or a plain DRF class
such as IsAuthenticated. `python manage.py list_api_access` prints every endpoint with its
rule, which is the quickest way to review access or compare it with the frontend.

Changing who may use a feature means editing the `groups` of its rule below. Adding a new
kind of access means adding a rule class here - never attaching requirements to the view
function (`some_view.required_groups = [...]`): DRF never hands the function to permission
classes, so such attributes are silently ignored. That mistake left most of the API open to
every logged-in user until September 2026. See docs/authentication_permissions.md.
"""

import logging

from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)


class Groups:
    """
    LDAP group names (the group's cn, case-sensitive) that access rules refer to.
    Mirrored into Django groups at login by django-auth-ldap.
    """

    ADMIN = "ADMIN"
    VERWALTUNG = "VERWALTUNG"
    HEIMRAT = "Heimrat"
    INFOREFERAT = "Inforeferat"
    NETZWERKREFERAT = "Netzwerkreferat"
    ZIMMERREFERAT = "Zimmerreferat"
    FINANZENREFERAT = "Finanzenreferat"
    SCHLICHTUNGSREFERAT = "Schlichtungsreferat"
    HSV_VERTRETER = "HSV-Vertreter"


def user_in_groups(user, groups):
    """
    True if the user is logged in and belongs to one of `groups`. ADMIN always passes.

    For views whose required groups depend on the object being accessed (see CheckedInView);
    everything else declares a GroupRule instead of calling this.
    """
    if not user or not user.is_authenticated:
        return False

    allowed = {Groups.ADMIN, *groups}
    return user.groups.filter(name__in=allowed).exists()


# --- Rule types ---

class AccessRule(BasePermission):
    """Base class of every rule a view may declare."""

    summary = ""

    @classmethod
    def describe(cls):
        """Who gets in, in words - shown by list_api_access."""
        return cls.summary


class Public(AccessRule):
    """No login required. Only for login / password reset and the Pi scan monitor."""

    summary = "anyone, no login"

    def has_permission(self, request, view):
        return True


class LoggedIn(AccessRule):
    """
    Any logged-in account. Meant for self-service endpoints that only ever touch the caller's
    own data (looked up via request.user) and for data every resident may see. Subtenants are
    still kept out by SubtenantApiGuardMiddleware.
    """

    summary = "any logged-in account"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class CheckedInView(LoggedIn):
    """
    Any logged-in account at the door; the view itself decides per object who may continue
    (e.g. the admin groups stored on an attendance event, or the department a signature
    belongs to), using user_in_groups(). Anyone declaring this owns that check.
    """

    summary = "logged in + per-object check inside the view"


class GroupRule(AccessRule):
    """
    Members of any of `groups`, plus ADMIN. Subclass it to name a new audience; a subclass
    without groups is rejected at import time rather than silently letting nobody - or
    everybody - in.
    """

    groups = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.groups:
            raise TypeError(f"{cls.__name__} must list at least one group.")

    @classmethod
    def describe(cls):
        return ", ".join([*cls.groups, Groups.ADMIN])

    def has_permission(self, request, view):
        allowed = user_in_groups(request.user, self.groups)
        if not allowed and request.user and request.user.is_authenticated:
            # Names who was refused where, so a report of "it says forbidden" can be traced
            # to the rule and the missing group (often: groups not re-synced since last login).
            logger.warning(
                f"Access denied by {type(self).__name__}: '{request.user.username}' is not in "
                f"{self.describe()} ({request.path})."
            )
        return allowed


class IsSubtenant(AccessRule):
    """Only accounts that belong to a subtenant."""

    summary = "subtenant accounts only"

    def has_permission(self, request, view):
        from .utils.subtenant_utils import is_subtenant_account

        return is_subtenant_account(request.user)


class DeviceTokenInvalid(APIException):
    status_code = 401
    # A dict detail is returned as the body unchanged - the Pi agent has always received this.
    default_detail = {"error": "Unauthorized."}


class HasDeviceToken(AccessRule):
    """
    Only the Pi print agent, which sends settings.DEVICE_AGENT_TOKEN as
    "Authorization: Bearer <token>" or "X-Device-Token: <token>". If no token is configured,
    every request is refused so print documents cannot leak by accident.
    """

    summary = "Pi print agent (device token)"

    def has_permission(self, request, view):
        expected = getattr(settings, 'DEVICE_AGENT_TOKEN', None)
        if not expected:
            logger.warning("DEVICE_AGENT_TOKEN not configured; rejecting agent request.")
            raise DeviceTokenInvalid()

        auth = request.META.get('HTTP_AUTHORIZATION', '')
        token = auth[len('Bearer '):].strip() if auth.startswith('Bearer ') else ''
        if not token:
            token = request.META.get('HTTP_X_DEVICE_TOKEN', '').strip()

        if not token or token != expected:
            raise DeviceTokenInvalid()
        return True


# --- Group rules: who may use which part of SmartDorm ---
# Keep these in step with the route and tab groups in the frontend (routesConfig.tsx and the
# `authGroups` of the tabbed pages). ADMIN is always allowed and is not listed.

class IsVerwaltung(GroupRule):
    """The Verwaltung area: tenants, subtenants, departures, claims, parcels, printer admin."""

    groups = (Groups.VERWALTUNG,)


class IsHeimrat(GroupRule):
    """Heimrat page: engagement applications and the semester switch with its LDAP sync."""

    groups = (Groups.HEIMRAT,)


class IsSemesterManager(GroupRule):
    """The global semester / application switches on the Heimrat page."""

    groups = (Groups.HEIMRAT, Groups.NETZWERKREFERAT)


class IsEngagementManager(GroupRule):
    """Referate page: create, edit and compensate engagements."""

    groups = (Groups.HEIMRAT, Groups.INFOREFERAT)


class IsNetworkAdmin(GroupRule):
    """Netzwerkreferat page: departments, LDAP roles, logs."""

    groups = (Groups.NETZWERKREFERAT,)


class CanViewResidentOverview(GroupRule):
    """Bewohnerübersicht: the resident overview, Referate overview and CSV download tabs."""

    groups = (
        Groups.HEIMRAT, Groups.INFOREFERAT, Groups.ZIMMERREFERAT,
        Groups.FINANZENREFERAT, Groups.SCHLICHTUNGSREFERAT,
    )


class CanViewResidentEngagements(GroupRule):
    """Resident engagement table: the overview tab plus the HSV-Vertreter tab."""

    groups = (*CanViewResidentOverview.groups, Groups.HSV_VERTRETER)


class CanViewResidentStatistics(GroupRule):
    """Bewohnerübersicht: the statistics tab."""

    groups = (
        Groups.HEIMRAT, Groups.INFOREFERAT, Groups.ZIMMERREFERAT,
        Groups.FINANZENREFERAT, Groups.HSV_VERTRETER,
    )
