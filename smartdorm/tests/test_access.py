"""
Access control tests: who may call which API endpoint.

These run without a database (SimpleTestCase): permissions are decided before a view touches
any data, so fake users are enough - and the test DB cannot be built anyway, because the
legacy `managed = False` tables are never created in it.

    python manage.py test smartdorm.tests.test_access

When a change to access is intended, the snapshot test fails and shows the difference;
regenerate the snapshot with `python manage.py list_api_access --write-snapshot` and let the
reviewer look at the diff of smartdorm/tests/api_access.txt.
"""

import difflib
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, override_settings
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from smartdorm.access_inventory import SNAPSHOT_PATH, iter_api_endpoints, render_access_table
from smartdorm.checks import check_api_access_rules
from smartdorm.permissions import (
    CheckedInView, GroupRule, Groups, HasDeviceToken, IsSubtenant, IsVerwaltung, LoggedIn, Public,
    user_in_groups,
)
from smartdorm.serializers import TenantSerializer
from smartdorm.views import attendance_views, department_views

factory = APIRequestFactory()


class FakeUser:
    """A logged-in user with the given groups, answering group lookups without the database."""

    is_authenticated = True

    def __init__(self, *groups, employee_type="TENANT"):
        self.username = "probe"
        self.first_name = employee_type  # employeeType, as mapped from LDAP
        self.groups = SimpleNamespace(
            filter=lambda name__in: SimpleNamespace(exists=lambda: bool(set(groups) & set(name__in)))
        )


def passes(endpoint, user, **headers):
    """Runs DRF's permission check for `endpoint` exactly as a real request would - but not the view."""
    request = factory.generic(endpoint.methods[0], "/" + endpoint.path, **headers)
    if user is not None:
        force_authenticate(request, user=user)

    view = endpoint.view_class()
    view.request = view.initialize_request(request)
    try:
        view.check_permissions(view.request)
    except APIException:
        return False
    return True


# --- The rules themselves ---

class GroupRuleTests(SimpleTestCase):
    class OnlyHeimrat(GroupRule):
        groups = (Groups.HEIMRAT,)

    def allows(self, user):
        request = SimpleNamespace(user=user, path="/api/test/")
        return self.OnlyHeimrat().has_permission(request, view=None)

    def test_members_and_admin_get_in(self):
        self.assertTrue(self.allows(FakeUser(Groups.HEIMRAT)))
        self.assertTrue(self.allows(FakeUser(Groups.ADMIN)))

    def test_everyone_else_stays_out(self):
        with self.assertLogs("smartdorm.permissions", "WARNING"):
            self.assertFalse(self.allows(FakeUser()))
            self.assertFalse(self.allows(FakeUser(Groups.NETZWERKREFERAT)))
        self.assertFalse(self.allows(AnonymousUser()))

    def test_a_refusal_names_the_user_the_rule_and_the_path(self):
        with self.assertLogs("smartdorm.permissions", "WARNING") as logs:
            self.allows(FakeUser(Groups.NETZWERKREFERAT))
        self.assertIn("OnlyHeimrat: 'probe' is not in Heimrat, ADMIN (/api/test/)", logs.output[0])

    def test_group_names_are_case_sensitive(self):
        request = SimpleNamespace(user=FakeUser("Verwaltung"), path="/api/test/")
        with self.assertLogs("smartdorm.permissions", "WARNING"):
            self.assertFalse(IsVerwaltung().has_permission(request, None))

    def test_a_rule_without_groups_is_rejected_at_definition(self):
        with self.assertRaises(TypeError):
            class Nobody(GroupRule):
                pass


class UserInGroupsTests(SimpleTestCase):
    def test_matches_any_group_and_always_admin(self):
        self.assertTrue(user_in_groups(FakeUser("Barreferat"), ["Tutoren", "Barreferat"]))
        self.assertTrue(user_in_groups(FakeUser(Groups.ADMIN), []))
        self.assertFalse(user_in_groups(FakeUser("Barreferat"), ["Werkreferat"]))
        self.assertFalse(user_in_groups(AnonymousUser(), ["Werkreferat"]))


class BasicRuleTests(SimpleTestCase):
    def allows(self, rule, user):
        return rule().has_permission(SimpleNamespace(user=user), view=None)

    def test_public_needs_no_login(self):
        self.assertTrue(self.allows(Public, AnonymousUser()))

    def test_logged_in_rules_need_a_login(self):
        for rule in (LoggedIn, CheckedInView):
            self.assertTrue(self.allows(rule, FakeUser()))
            self.assertFalse(self.allows(rule, AnonymousUser()))

    def test_is_subtenant_asks_the_subtenant_helper(self):
        with mock.patch("smartdorm.utils.subtenant_utils.is_subtenant_account", return_value=True):
            self.assertTrue(self.allows(IsSubtenant, FakeUser()))
        with mock.patch("smartdorm.utils.subtenant_utils.is_subtenant_account", return_value=False):
            self.assertFalse(self.allows(IsSubtenant, FakeUser()))


@override_settings(DEVICE_AGENT_TOKEN="s3cret")
class HasDeviceTokenTests(SimpleTestCase):
    def check(self, **headers):
        request = SimpleNamespace(user=AnonymousUser(), META=headers)
        return HasDeviceToken().has_permission(request, view=None)

    def test_accepts_the_token_in_either_header(self):
        self.assertTrue(self.check(HTTP_AUTHORIZATION="Bearer s3cret"))
        self.assertTrue(self.check(HTTP_X_DEVICE_TOKEN="s3cret"))

    def test_rejects_wrong_or_missing_token_with_the_agents_401(self):
        for headers in ({}, {"HTTP_AUTHORIZATION": "Bearer wrong"}, {"HTTP_X_DEVICE_TOKEN": ""}):
            with self.assertRaises(APIException) as raised:
                self.check(**headers)
            self.assertEqual(raised.exception.status_code, 401)
            self.assertEqual(raised.exception.detail, {"error": "Unauthorized."})

    @override_settings(DEVICE_AGENT_TOKEN="")
    def test_rejects_everything_when_no_token_is_configured(self):
        with self.assertRaises(APIException), self.assertLogs("smartdorm.permissions", "WARNING"):
            self.check(HTTP_X_DEVICE_TOKEN="")


# --- The real API, through DRF's own permission check ---

@override_settings(DEVICE_AGENT_TOKEN="configured-but-not-sent")
class EndpointAccessTests(SimpleTestCase):
    """Who gets through each endpoint's door, for typical accounts."""

    ANY_LOGIN = {"Public", "LoggedIn", "CheckedInView"}

    def setUp(self):
        for patcher in (
            mock.patch("smartdorm.utils.subtenant_utils.is_subtenant_account", return_value=False),
            mock.patch("smartdorm.permissions.logger"),  # refusals are expected here
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def assert_reaches_exactly(self, user, expected_rules):
        for endpoint in iter_api_endpoints():
            with self.subTest(endpoint=endpoint.path):
                self.assertEqual(passes(endpoint, user), endpoint.rule.__name__ in expected_rules)

    def test_anonymous_only_reaches_public_endpoints(self):
        self.assert_reaches_exactly(None, {"Public"})

    def test_a_tenant_without_roles_reaches_no_group_endpoint(self):
        self.assert_reaches_exactly(FakeUser("tenant"), self.ANY_LOGIN)

    def test_the_verwaltung_account_reaches_the_verwaltung_area(self):
        self.assert_reaches_exactly(FakeUser(Groups.VERWALTUNG, employee_type="DEPARTMENT"), self.ANY_LOGIN | {"IsVerwaltung"})

    def test_admin_reaches_every_group_endpoint_despite_being_a_tenant_account(self):
        everything_but_devices_and_subtenants = {
            e.rule.__name__ for e in iter_api_endpoints()
        } - {"HasDeviceToken", "IsSubtenant"}
        self.assert_reaches_exactly(FakeUser("tenant", Groups.ADMIN), everything_but_devices_and_subtenants)


class PerObjectCheckTests(SimpleTestCase):
    """CheckedInView endpoints decide inside the view; these cover the deciding helpers."""

    def test_signatures_are_limited_to_their_department(self):
        request = factory.get("/")
        force_authenticate(request, user=FakeUser("Barreferat"))
        response = department_views.list_department_signatures_view(request, department_slug="werk")
        self.assertEqual(response.status_code, 403)

    def test_event_admins_come_from_the_event(self):
        event = SimpleNamespace(admin_groups=[Groups.HEIMRAT])
        self.assertTrue(attendance_views._is_event_admin(SimpleNamespace(user=FakeUser(Groups.HEIMRAT)), event))
        self.assertFalse(attendance_views._is_event_admin(SimpleNamespace(user=FakeUser("Barreferat")), event))

    def test_an_event_without_a_group_list_is_admin_only(self):
        event = SimpleNamespace(admin_groups=None)
        self.assertFalse(attendance_views._is_event_admin(SimpleNamespace(user=FakeUser(Groups.HEIMRAT)), event))
        self.assertTrue(attendance_views._is_event_admin(SimpleNamespace(user=FakeUser(Groups.ADMIN)), event))


class TenantSerializerTests(SimpleTestCase):
    def test_username_cannot_be_changed(self):
        # A writable username would let an edit repoint the record - and a credential resend -
        # at another LDAP account.
        self.assertTrue(TenantSerializer().fields["username"].read_only)


# --- The guards that keep it this way ---

@api_view(["GET"])
@permission_classes([LoggedIn])
def declared_view(request):
    return Response()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def old_style_view(request):
    return Response()


@api_view(["GET"])
def undeclared_view(request):
    return Response()


@api_view(["GET"])
@permission_classes([LoggedIn, IsVerwaltung])
def two_rules_view(request):
    return Response()


urlpatterns = [
    path("api/declared/", declared_view),
    path("api/old-style/", old_style_view),
    path("api/undeclared/", undeclared_view),
    path("api/two-rules/", two_rules_view),
    path("outside-the-api/", undeclared_view),
]


@override_settings(ROOT_URLCONF=__name__)
class StartupCheckTests(SimpleTestCase):
    def test_flags_every_api_view_without_exactly_one_rule(self):
        flagged = {error.msg.split(" (")[0].rsplit(".", 1)[-1] for error in check_api_access_rules(None)}
        self.assertEqual(flagged, {"old_style_view", "undeclared_view", "two_rules_view"})


class RealApiTests(SimpleTestCase):
    def test_every_endpoint_declares_a_rule(self):
        self.assertEqual(check_api_access_rules(None), [])

    def test_access_matches_the_reviewed_snapshot(self):
        expected = SNAPSHOT_PATH.read_text()
        actual = render_access_table()
        if actual != expected:
            diff = "".join(difflib.unified_diff(
                expected.splitlines(keepends=True), actual.splitlines(keepends=True),
                fromfile="api_access.txt (reviewed)", tofile="current code",
            ))
            self.fail(
                "API access differs from smartdorm/tests/api_access.txt.\n"
                "If intended, run `python manage.py list_api_access --write-snapshot` and commit the "
                "snapshot so the change gets reviewed.\n\n" + diff
            )
