from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
import logging
import ldap
from ldap.filter import escape_filter_chars

from smartdorm.models import Tenant, Engagement, GlobalAppSettings, Department
from smartdorm import config as app_config

# Configure logging
logger = logging.getLogger('smartdorm')

class Command(BaseCommand):
    help = 'Recalculates points, sublet duration, extensions, and synchronizes LDAP roles for current tenants.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate LDAP changes without executing them.',
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting nightly tenant statistics and LDAP sync...")
        logger.info("Starting nightly tenant statistics and LDAP sync.")
        
        self.dry_run = options['dry_run']
        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: No LDAP changes will be applied."))

        today = timezone.now().date()
        
        # Load Global Settings for Semester checks
        try:
            print("Loading GlobalAppSettings...")
            app_settings = GlobalAppSettings.load()
            print(app_settings)
            current_semester = app_settings.current_semester
        except Exception:
            logger.error("Could not load GlobalAppSettings. Aborting.")
            logger.error("Traceback:", exc_info=True)
            return

        # Fetch Tenants
        tenants = Tenant.objects.filter(
            move_in__lte=today,
            move_out__gte=today
        ).prefetch_related(
            'engagement_set',
            'engagement_set__department',
            'subtenant_set',
            'claim_set'
        )

        # 1. Recalculate Stats (Points, Sublets, Extensions)
        self.sync_stats(tenants)

        # 2. Sync LDAP Roles
        self.sync_ldap_roles(tenants, current_semester)

        self.stdout.write(self.style.SUCCESS("Nightly routine finished."))

    def sync_stats(self, tenants):
        """Recalculates DB statistics for tenants."""
        updates_count = 0
        with transaction.atomic():
            for tenant in tenants:
                changes = []

                # --- Points ---
                calculated_points = Decimal('0.00')
                for eng in tenant.engagement_set.all():
                    if eng.compensate:
                        calculated_points += eng.points

                if (tenant.current_points or Decimal('0.00')) != calculated_points:
                    changes.append(f"Points: {tenant.current_points} -> {calculated_points}")
                    tenant.current_points = calculated_points

                # --- Sublet Duration (Months) ---
                total_sublet_days = 0
                for sub in tenant.subtenant_set.all():
                    if sub.move_out and sub.move_in:
                        duration = (sub.move_out - sub.move_in).days
                        if duration > 0:
                            total_sublet_days += duration

                calculated_sublet_months = 0.0
                if total_sublet_days > 0: 
                    # round to nearest half month
                    calculated_sublet_months = round((total_sublet_days / 30.0) * 2) / 2
                
                if (tenant.sublet or 0.0) != calculated_sublet_months:                
                    changes.append(f"Sublet: {tenant.sublet} -> {calculated_sublet_months} (days: {total_sublet_days})")
                    tenant.sublet = calculated_sublet_months

                # --- Extensions ---
                approved_claims = [c for c in tenant.claim_set.all() if c.status == 'APPROVED' and c.type == 'EXTENSION']
                calculated_extensions = len(approved_claims)
                
                if (tenant.extension or 0) != calculated_extensions:
                    changes.append(f"Extensions: {tenant.extension} -> {calculated_extensions}")
                    tenant.extension = calculated_extensions
                
                if changes:
                    if(not self.dry_run):
                        tenant.save(update_fields=['current_points', 'sublet', 'extension'])
                    updates_count += 1
                    self.stdout.write(f"Stats Updated for {tenant.username}: {', '.join(changes)}")
                    
        self.stdout.write(f"Stats calculation complete. {updates_count} tenants updated.")

    def sync_ldap_roles(self, tenants, current_semester):
        """Synchronizes LDAP groups based on tenant status and engagements."""
        
        # --- LDAP Connection Setup ---
        ldap_uri = settings.AUTH_LDAP_SERVER_URI
        admin_dn = settings.AUTH_LDAP_BIND_DN
        admin_pw = settings.AUTH_LDAP_BIND_PASSWORD
        
        try:
            con = ldap.initialize(ldap_uri)
            con.protocol_version = ldap.VERSION3
            con.simple_bind_s(admin_dn, admin_pw)
        except ldap.LDAPError as e:
            logger.error(f"LDAP Connection failed: {e}")
            return

        try:
            # --- 1. Identify "Managed" Groups ---
            # We must identify which groups allow automatic removal. 
            # We do NOT want to remove 'cn=admin' or manual groups.
            
            managed_groups_dn = set()
            
            # A. Default Groups
            for g in app_config.DEFAULT_TENANT_LDAP_GROUPS:
                managed_groups_dn.add(g.lower())

            # B. The HSV Group
            hsv_group_dn = "cn=HSV,ou=groups2,dc=schollheim,dc=net".lower()
            managed_groups_dn.add(hsv_group_dn)

            # C. All Floor Groups (H1EG to H2F5, etc)
            # We query the DB for all unique floors to build this list dynamically
            all_floors = Tenant.objects.values_list('current_floor', flat=True).distinct()
            for fl in all_floors:
                if fl:
                    managed_groups_dn.add(f"cn={fl},ou=groups2,dc=schollheim,dc=net".lower())

            # D. All Department Groups
            all_depts = Department.objects.all()
            for dept in all_depts:
                # We need to generate the potential CNs.
                # Since the logic depends on tenant floor for 'Flursprecher', 
                # we add the base name, and for Flursprecher, we add all specific floor combos.
                base_name = self._get_base_dept_name(dept.full_name)
                managed_groups_dn.add(f"cn={base_name},ou=groups2,dc=schollheim,dc=net".lower())
                
                if base_name.lower() == 'flursprecher':
                    for fl in all_floors:
                        if fl:
                            managed_groups_dn.add(f"cn=flursprecher-{fl},ou=groups2,dc=schollheim,dc=net".lower())

            self.stdout.write(f"Identified {len(managed_groups_dn)} managed system groups.")

            # --- 2. Process Tenants ---
            for tenant in tenants:
                if not tenant.username:
                    continue

                user_dn = f"cn={tenant.username},ou=users,dc=schollheim,dc=net"
                
                # --- A. Calculate SHOULD HAVE Groups ---
                should_have_dns = set()

                # 1. Defaults
                for g in app_config.DEFAULT_TENANT_LDAP_GROUPS:
                    should_have_dns.add(g.lower())

                # 2. Floor
                if tenant.current_floor:
                    should_have_dns.add(f"cn={tenant.current_floor},ou=groups2,dc=schollheim,dc=net".lower())

                # 3. Engagements
                active_engagements = [e for e in tenant.engagement_set.all() if e.semester == current_semester]
                
                if active_engagements:
                    # Add HSV group if they have ANY engagement
                    should_have_dns.add(hsv_group_dn)

                    for eng in active_engagements:
                        group_cn = self._get_ldap_group_name(eng.department.full_name, tenant)
                        should_have_dns.add(f"cn={group_cn},ou=groups2,dc=schollheim,dc=net".lower())

                # --- B. Fetch ACTUAL Groups ---
                current_group_dns = self._get_user_groups(con, user_dn)

                # --- C. Calculate Diff ---
                groups_to_add = should_have_dns - current_group_dns
                
                # Only remove groups that are in our "Managed" list.
                groups_to_remove = (current_group_dns - should_have_dns).intersection(managed_groups_dn)

                # --- D. Execute Changes ---
                if groups_to_add:
                    for g_dn in groups_to_add:
                        self._add_to_group(con, user_dn, g_dn, tenant.username)
                
                if groups_to_remove:
                    for g_dn in groups_to_remove:
                        self._remove_from_group(con, user_dn, g_dn, tenant.username)

        finally:
            con.unbind_s()

    def _get_base_dept_name(self, full_name):
        name = full_name.split(' ')[0]
        name = name.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
        return name

    def _get_ldap_group_name(self, full_name, tenant):
        """
        Replicates logic from engagement_views to determine group CN.
        Handles the 'Flursprecher' edge case.
        """
        name = self._get_base_dept_name(full_name)
        
        # Special case for Flursprecher
        if name.lower() == 'flursprecher' and tenant.current_floor:
            name += f"-{tenant.current_floor}"
        
        return name

    def _get_user_groups(self, con, user_dn):
        """
        Finds all groups where member=<user_dn>.
        Searches in groups, groups2, and roles OUs.
        """
        found_groups = set()
        search_bases = [
            "ou=groups,dc=schollheim,dc=net",
            "ou=groups2,dc=schollheim,dc=net",
            "ou=roles,dc=schollheim,dc=net"
        ]
        
        # Filter: (member=cn=user,ou=users...)
        search_filter = f"(member={escape_filter_chars(user_dn)})"

        for base in search_bases:
            try:
                results = con.search_s(base, ldap.SCOPE_SUBTREE, search_filter, ['distinguishedName'])
                for dn, attrs in results:
                    if dn:
                        found_groups.add(dn.lower())
            except ldap.NO_SUCH_OBJECT:
                continue
            except ldap.LDAPError as e:
                logger.error(f"Error searching groups in {base}: {e}")
        
        return found_groups

    def _add_to_group(self, con, user_dn, group_dn, username):
        if self.dry_run:
            logger.info(f"[DRY RUN] Would ADD {username} to {group_dn}")
            return

        try:
            mod_list = [(ldap.MOD_ADD, 'member', [user_dn.encode('utf-8')])]
            con.modify_s(group_dn, mod_list)
            logger.info(f"LDAP: Added {username} to {group_dn}")
        except ldap.TYPE_OR_VALUE_EXISTS:
            pass # Already there
        except ldap.NO_SUCH_OBJECT:
            logger.error(f"LDAP: Group {group_dn} does not exist. Cannot add {username}.")
        except Exception as e:
            logger.error(f"LDAP: Failed to add {username} to {group_dn}: {e}")

    def _remove_from_group(self, con, user_dn, group_dn, username):
        if self.dry_run:
            logger.info(f"[DRY RUN] Would REMOVE {username} from {group_dn}")
            return

        try:
            mod_list = [(ldap.MOD_DELETE, 'member', [user_dn.encode('utf-8')])]
            con.modify_s(group_dn, mod_list)
            logger.info(f"LDAP: Removed {username} from {group_dn}")
        except ldap.NO_SUCH_ATTRIBUTE:
            pass # Already gone
        except ldap.NO_SUCH_OBJECT:
            logger.error(f"LDAP: Group {group_dn} does not exist. Cannot remove {username}.")
        except Exception as e:
            logger.error(f"LDAP: Failed to remove {username} from {group_dn}: {e}")