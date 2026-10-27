"""The dev accounts for trying each role, and the login page's list of them. No database needed."""

from datetime import date
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from smartdorm import permissions
from smartdorm.dev_accounts import DEV_ACCOUNTS, DUMMY_NAME, EMAIL_DOMAIN, is_dev_email, non_test_targets
from smartdorm.management.commands.recalculate_tenant_stats import Command as NightlySyncCommand
from smartdorm.tests.test_access import FakeUser
from smartdorm.views.auth_views import dev_accounts_view


class DevAccountTests(SimpleTestCase):
    @mock.patch("smartdorm.permissions.logger")  # refusals are expected
    def test_every_group_rule_can_be_tried_with_a_dev_account(self, _):
        for rule in permissions.GroupRule.__subclasses__():
            with self.subTest(rule=rule.__name__):
                passing = [
                    a.username for a in DEV_ACCOUNTS
                    if rule().has_permission(SimpleNamespace(user=FakeUser(*a.groups), path="/"), view=None)
                ]
                self.assertTrue(passing)

    def test_only_resident_accounts_get_a_tenant_record(self):
        with_record = {a.username for a in DEV_ACCOUNTS if a.has_tenant_record}
        self.assertIn("dev-admin", with_record)
        self.assertNotIn("dev-verwaltung", with_record)  # the real Verwaltung account has none either
        self.assertNotIn("dev-untermieter", with_record)  # a tenant record would make it a resident

    def test_dummy_tenant_data_is_recognisable_as_such(self):
        for account in DEV_ACCOUNTS:
            fields = account.dummy_tenant_fields(date(2026, 1, 1))
            self.assertEqual(fields["name"], DUMMY_NAME)
            self.assertEqual(fields["surname"], account.username)
            self.assertTrue(fields["email"].endswith("@" + EMAIL_DOMAIN))
            self.assertLess(fields["move_in"], date(2026, 1, 1))
            self.assertGreater(fields["move_out"], date(2026, 1, 1))  # a current resident

    def test_usernames_are_unique_and_marked_as_dev(self):
        usernames = [a.username for a in DEV_ACCOUNTS]
        self.assertEqual(len(usernames), len(set(usernames)))
        self.assertTrue(all(u.startswith("dev-") for u in usernames))


class NightlySyncTests(SimpleTestCase):
    """The nightly LDAP sync must leave the dev accounts' role groups alone - they have no engagements."""

    def test_recognises_dev_mails_only(self):
        for account in DEV_ACCOUNTS:
            self.assertTrue(is_dev_email(account.email))
        self.assertTrue(is_dev_email(" DEV-Heimrat@SMARTDORM-DEV.INVALID "))
        self.assertFalse(is_dev_email("someone@example.com"))
        self.assertFalse(is_dev_email("someone@smartdorm-dev.invalid.example.com"))
        self.assertFalse(is_dev_email(None))

    def tenant(self, username, email):
        return SimpleNamespace(
            username=username, email=email, current_floor=None,
            engagement_set=SimpleNamespace(all=lambda: []),
        )

    @mock.patch("smartdorm.management.commands.recalculate_tenant_stats.custom_role_dns_by_username", return_value={})
    @mock.patch("smartdorm.management.commands.recalculate_tenant_stats.Department")
    @mock.patch("smartdorm.management.commands.recalculate_tenant_stats.Room")
    @mock.patch("smartdorm.management.commands.recalculate_tenant_stats.ldap")
    def test_skips_dev_tenants_but_still_syncs_real_ones(self, _ldap, room, department, _custom_roles):
        room.objects.values_list.return_value.distinct.return_value = []
        department.objects.all.return_value = [SimpleNamespace(full_name="Heimrat")]
        heimrat_dn = "cn=heimrat,ou=groups2,dc=schollheim,dc=net"

        command = NightlySyncCommand()
        command.dry_run = False
        command.revoke_expired_role_assignments = mock.Mock()
        command.sync_subtenant_ldap_roles = mock.Mock()
        command._get_user_groups = mock.Mock(return_value={heimrat_dn})
        command._add_to_group = mock.Mock()
        command._remove_from_group = mock.Mock()

        tenants = [self.tenant("dev-heimrat", "dev-heimrat@" + EMAIL_DOMAIN), self.tenant("j.doe", "j.doe@example.com")]
        command.sync_ldap_roles(tenants, current_semester="WS26", today=date(2026, 10, 27))

        synced = {call.args[3] for call in command._add_to_group.call_args_list + command._remove_from_group.call_args_list}
        self.assertEqual(synced, {"j.doe"})
        command._remove_from_group.assert_called_once_with(mock.ANY, mock.ANY, heimrat_dn, "j.doe")


class TestTargetGuardTests(SimpleTestCase):
    """dev_accounts must only ever write to the test LDAP and a test database."""

    def test_accepts_the_test_systems(self):
        self.assertEqual(non_test_targets("ldap://ldap-test.schollheim.net:389", "db-test-smartdorm-V2.schollheim.net"), [])
        self.assertEqual(non_test_targets("ldap://LDAP-TEST.schollheim.net", "localhost"), [])

    def test_refuses_production_or_unknown_systems(self):
        self.assertEqual(len(non_test_targets("ldap://ldap.schollheim.net:389", "db-test-smartdorm-V2.schollheim.net")), 1)
        self.assertEqual(len(non_test_targets("ldap://ldap-test.schollheim.net", "db.schollheim.net")), 1)
        self.assertEqual(len(non_test_targets("ldap://ldap-test.schollheim.net.evil.org", "localhost")), 1)
        self.assertEqual(len(non_test_targets(None, None)), 2)


class DevAccountsEndpointTests(SimpleTestCase):
    def call(self):
        return dev_accounts_view(APIRequestFactory().get("/api/auth/dev-accounts/"))

    @override_settings(SHOW_DEV_ACCOUNTS=False)
    def test_hidden_unless_switched_on(self):
        self.assertEqual(self.call().status_code, 404)

    @override_settings(SHOW_DEV_ACCOUNTS=True)
    def test_lists_usernames_but_never_a_password(self):
        response = self.call()
        self.assertEqual(response.status_code, 200)
        self.assertEqual([a["username"] for a in response.data], [a.username for a in DEV_ACCOUNTS])
        self.assertEqual({key for entry in response.data for key in entry}, {"username", "description"})
