import uuid
from getpass import getpass

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from smartdorm.dev_accounts import DEV_ACCOUNTS, non_test_targets
from smartdorm.models import Tenant
from smartdorm.utils import ldap_utils


class Command(BaseCommand):
    help = (
        "Creates (or refreshes) one LDAP account per role in the test LDAP, all sharing one "
        "password, plus dummy tenant records for the resident accounts, so every role can be "
        "tried out. --delete removes them again."
    )

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true", help="Remove the dev accounts.")
        parser.add_argument("--password", help="Password for all dev accounts (asked for if omitted).")
        parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Refusing to run: PRODUCTION is set. Dev accounts belong in the test LDAP only.")

        database = settings.DATABASES["default"]
        problems = non_test_targets(settings.AUTH_LDAP_SERVER_URI, database["HOST"])
        if problems:
            raise CommandError("Refusing to run: " + "; ".join(problems) + ". Is the right .env loaded?")

        action = "DELETE" if options["delete"] else "create or refresh"
        self.stdout.write(
            f"This will {action} {len(DEV_ACCOUNTS)} accounts in {settings.AUTH_LDAP_SERVER_URI} and their "
            f"dummy tenant records in the database {database['NAME']} on {database['HOST']}:"
        )
        for account in DEV_ACCOUNTS:
            self.stdout.write(f"  {account.username:<28} {account.description}")
        if not options["yes"] and input("Continue? [y/N] ").strip().lower() != "y":
            raise CommandError("Aborted.")

        group_dns = {group["cn"]: group["dn"] for group in ldap_utils.list_ldap_groups()}
        if options["delete"]:
            self.delete_accounts(group_dns)
            self.delete_tenant_records()
        else:
            self.create_accounts(group_dns, options["password"] or self.ask_password())
            self.sync_tenant_records()

    def ask_password(self):
        password = getpass("Password for all dev accounts: ")
        if not password or password != getpass("Repeat: "):
            raise CommandError("Passwords are empty or do not match.")
        return password

    def is_dev_account(self, account):
        """Only touch accounts we created - a real person could be called dev-something too."""
        mails = ldap_utils.get_ldap_user_emails(account.username)
        if mails is None:
            return None  # does not exist
        return account.email in mails

    def resolve_groups(self, account, group_dns):
        missing = [cn for cn in account.groups if cn not in group_dns]
        if missing:
            self.stderr.write(f"  {account.username}: group(s) not found in this LDAP, skipped: {', '.join(missing)}")
        return [group_dns[cn] for cn in account.groups if cn in group_dns]

    def create_accounts(self, group_dns, password):
        for account in DEV_ACCOUNTS:
            dns = self.resolve_groups(account, group_dns)
            existing = self.is_dev_account(account)

            if existing is None:
                ldap_utils.create_ldap_user(
                    account.username, password, "Dev", account.description, account.email,
                    group_dns=dns, userType=account.employee_type,
                )
                self.stdout.write(f"  created   {account.username}")
            elif existing:
                ldap_utils.update_ldap_password(account.username, password)
                ldap_utils.update_ldap_user_attributes(account.username, employee_type=account.employee_type)
                for dn in dns:
                    ldap_utils.add_user_to_group(account.username, dn)
                self.stdout.write(f"  refreshed {account.username}")
            else:
                self.stderr.write(f"  {account.username} exists but is not a dev account - left untouched.")

    def delete_accounts(self, group_dns):
        for account in DEV_ACCOUNTS:
            if not self.is_dev_account(account):
                continue
            # Deleting an LDAP entry leaves it listed as a member of its groups.
            for dn in self.resolve_groups(account, group_dns):
                ldap_utils.remove_user_from_group(account.username, dn)
            ldap_utils.delete_ldap_user(account.username)
            User.objects.filter(username=account.username).delete()  # the mirrored Django user
            self.stdout.write(f"  deleted   {account.username}")

    @transaction.atomic
    def sync_tenant_records(self):
        """Gives every resident dev account a tenant record, resetting it to the dummy data."""
        today = timezone.now().date()
        for account in DEV_ACCOUNTS:
            if not account.has_tenant_record:
                continue

            fields = account.dummy_tenant_fields(today)
            records = Tenant.objects.filter(username=account.username)
            if records.exclude(email=account.email).exists():
                self.stderr.write(f"  tenant record '{account.username}' is not dev data - left untouched.")
            elif records.exists():
                records.update(**fields)
                self.stdout.write(f"  reset     tenant record {account.username}")
            else:
                # Legacy table without auto-increment - the same scheme create_new_tenant_view uses.
                next_id = (Tenant.objects.aggregate(max_id=Max("id"))["max_id"] or 0) + 1
                Tenant.objects.create(id=next_id, external_id=uuid.uuid4().hex, username=account.username, **fields)
                self.stdout.write(f"  created   tenant record {account.username}")

    def delete_tenant_records(self):
        for account in DEV_ACCOUNTS:
            # Deletes what was attached to it while testing too (engagements, print jobs, ...).
            deleted, _ = Tenant.objects.filter(username=account.username, email=account.email).delete()
            if deleted:
                self.stdout.write(f"  deleted   tenant record {account.username}")
