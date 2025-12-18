from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from dateutil.relativedelta import relativedelta
from datetime import timedelta, date
import sys

from smartdorm.models import Tenant, DepartmentExtension, Termination
from smartdorm.utils.helper import (
    recalculate_tenant_contract_dates, 
    get_closest_end_of_month
)
from smartdorm import config as app_config

class Command(BaseCommand):
    help = 'Verifies and migrates tenant contract dates to the new calculation logic.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant', 
            type=str, 
            help='Username of a specific tenant to verify'
        )
        parser.add_argument(
            '--all', 
            action='store_true', 
            help='Check all tenants (default checks only active/future)'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Starting Contract Date Verification..."))
        
        today = timezone.now().date()
        query = Tenant.objects.all().order_by('surname', 'name')
        
        if options['tenant']:
            query = query.filter(username=options['tenant'])
        elif not options['all']:
            # Default: Current and Future tenants
            query = query.filter(move_out__gte=today)

        changes_summary = []
        
        # Prefetch for performance
        tenants = query.prefetch_related('subtenant_set', 'department_extensions')
        
        total = tenants.count()
        self.stdout.write(f"Found {total} tenants to verify.\n")

        for tenant in tenants:
            # Skip if termination exists (Termination overrides everything anyway)
            if hasattr(tenant, 'termination_record'):
                continue

            self.verify_tenant(tenant, changes_summary)

        # --- Summary ---
        self.stdout.write(self.style.SUCCESS("\n--- MIGRATION SUMMARY ---"))
        if not changes_summary:
            self.stdout.write("No changes were made.")
        else:
            for line in changes_summary:
                self.stdout.write(line)
        self.stdout.write(self.style.SUCCESS("Verification complete."))

    def verify_tenant(self, tenant, summary_list):
        # 1. Calculate the components manually for display (The "Why")
        breakdown = self.get_calculation_breakdown(tenant)
        calculated_date = breakdown['final_date']
        current_db_date = tenant.move_out

        # If dates match, we are good
        if calculated_date == current_db_date:
            return

        # If mismatch, start interactive mode
        while True:
            self.print_breakdown(tenant, current_db_date, calculated_date, breakdown)
            
            self.stdout.write("\nOptions:")
            self.stdout.write("  [1] Accept NEW Date (Update DB to Calculated)")
            self.stdout.write("  [2] Accept OLD Date (Create 'Migration' Department Extension)")
            self.stdout.write("  [3] Analyze Subtenancies (Check if discrepancy is due to subtenants)")
            self.stdout.write("  [s] Skip")
            
            choice = input(f"Select option for {tenant.username} > ").strip().lower()

            if choice == '1':
                # Accept New
                recalculate_tenant_contract_dates(tenant) # This saves the tenant
                summary_list.append(f"[UPDATED] {tenant.username}: {current_db_date} -> {calculated_date}")
                self.stdout.write(self.style.SUCCESS("Date updated."))
                break

            elif choice == '2':
                # Accept Old -> Calculate difference in months and create extension
                success = self.handle_accept_old(tenant, current_db_date, calculated_date)
                if success:
                    summary_list.append(f"[MIGRATED] {tenant.username}: Kept {current_db_date} (Created Dept Extension)")
                    break
                else:
                    self.stdout.write(self.style.ERROR("Could not perfectly match old date. Try again or skip."))
            
            elif choice == '3':
                # Detailed Subtenancy Analysis
                self.analyze_subtenancy_impact(tenant, current_db_date, breakdown)
                input("\nPress Enter to return to menu...")
                # Loop continues, re-printing menu
            
            elif choice == 's':
                self.stdout.write(self.style.WARNING("Skipped."))
                break
            
            else:
                self.stdout.write(self.style.ERROR("Invalid option."))

    def get_calculation_breakdown(self, tenant):
        """
        Replicates logic from recalculate_tenant_contract_dates but returns components.
        """
        # A. Base
        base_move_out = tenant.move_in + timedelta(days=app_config.DEFAULT_CONTRACT_DURATION_DAYS)
        
        # B. Extensions
        extension_count = tenant.extension or 0
        total_extension_days = extension_count * app_config.DEFAULT_EXTENSION_DURATION_DAYS
        
        # C. Subtenants
        confirmed_subtenants = tenant.subtenant_set.filter(university_confirmation=True)
        sublet_days = 0
        for sub in confirmed_subtenants:
            if sub.move_out > sub.move_in:
                sublet_days += (sub.move_out - sub.move_in).days

        # D. Dept Extensions
        dept_months = tenant.department_extensions.aggregate(total=Sum('months'))['total'] or 0
        
        # E. Raw Calc
        raw_date = base_move_out + timedelta(days=sublet_days + total_extension_days)
        raw_date = raw_date + relativedelta(months=dept_months)
        
        # F. Final (End of Month)
        final_date = get_closest_end_of_month(raw_date)

        return {
            'base_end': base_move_out,
            'extensions_count': extension_count,
            'sublet_days': sublet_days,
            'dept_months': dept_months,
            'raw_date': raw_date,
            'final_date': final_date
        }

    def print_breakdown(self, tenant, current, calculated, b):
        self.stdout.write("\n" + "="*60)
        self.stdout.write(f"TENANT: {tenant.get_full_name()} ({tenant.username})")
        self.stdout.write(f"Room: {tenant.current_room}")
        self.stdout.write("-" * 60)
        self.stdout.write(f"Current DB Date:   {self.style.WARNING(str(current))}")
        self.stdout.write(f"New Calculated:    {self.style.SUCCESS(str(calculated))}")
        self.stdout.write("-" * 60)
        self.stdout.write("CALCULATION FACTORS:")
        self.stdout.write(f"  Move In:          {tenant.move_in}")
        self.stdout.write(f"  + Base Contract:  3 Years")
        self.stdout.write(f"  + Extensions:     {b['extensions_count']} x 1 Year")
        self.stdout.write(f"  + Subtenants:     {b['sublet_days']} days (from {tenant.subtenant_set.filter(university_confirmation=True).count()} confirmed subtenants)")
        self.stdout.write(f"  + Dept Ext:       {b['dept_months']} months")
        self.stdout.write(f"  = Raw Date:       {b['raw_date']}")
        self.stdout.write(f"  -> EOM Snap:      {b['final_date']}")
        self.stdout.write("="*60)

    def handle_accept_old(self, tenant, old_date, new_date):
        """
        Calculates the month difference needed to bridge New -> Old.
        Creates a DepartmentExtension.
        Verifies if the result matches.
        """
        # Calculate difference in months
        # We use relativedelta to get rough months
        diff = relativedelta(old_date, new_date)
        months_diff = diff.years * 12 + diff.months
        
        # Sometimes relativedelta is tricky with days (e.g. Jan 31 vs Feb 28).
        # If the old date is > new date, but months is 0, it might be just days diff, 
        # but DeptExtension only handles integers.
        # Check if we need to round up/down.
        
        # Simple heuristic: Try the calculated months, if it doesn't match, try +/- 1
        candidates = [months_diff, months_diff + 1, months_diff - 1]
        
        best_month_val = None
        
        # We need to simulate adding these months to the *current* configuration
        # The breakdown logic: raw_date + months
        # Note: We can't just add to new_date because snapping happens at the end.
        
        # Get base calc again
        breakdown = self.get_calculation_breakdown(tenant)
        # raw date (before EOM snap) from current breakdown
        base_raw = breakdown['raw_date'] 
        
        for m in candidates:
            test_raw = base_raw + relativedelta(months=m)
            test_final = get_closest_end_of_month(test_raw)
            if test_final == old_date:
                best_month_val = m
                break
        
        if best_month_val is None:
            self.stdout.write(self.style.ERROR(f"Cannot perfectly match {old_date} using integer months."))
            self.stdout.write(f"Closest would be {get_closest_end_of_month(base_raw + relativedelta(months=months_diff))}")
            confirm = input("Do you want to apply the closest approximation? (y/n): ")
            if confirm.lower() != 'y':
                return False
            best_month_val = months_diff

        if best_month_val == 0:
            self.stdout.write("Difference is less than a month (rounding error). No extension created, just saving current.")
            # Technically we accept the NEW date here because we can't extend by 0.5 months
            # But the user wanted 'Accept Old'. 
            # If the date differs by days but we cant fix it with months, we effectively force the new EOM logic.
            # However, if it's 0, it implies dates are same, which wouldn't trigger this menu.
            return False

        # Apply
        with transaction.atomic():
            DepartmentExtension.objects.create(
                tenant=tenant,
                months=best_month_val,
                note="(Auto generated during v2 migration) - Legacy Date Preservation"
            )
            # Recalculate to verify and save
            recalculate_tenant_contract_dates(tenant)
            
        self.stdout.write(self.style.SUCCESS(f"Created DepartmentExtension of {best_month_val} months."))
        return True

    def analyze_subtenancy_impact(self, tenant, current_db_date, breakdown):
        """
        Calculates what the date WOULD be if we only looked at Base + Extensions + Subtenants.
        Compares this to the DB date to see if subtenancies were the missing factor.
        """
        # Theoretical date with ONLY subtenancies (ignoring any existing Dept Extensions)
        # breakdown['raw_date'] includes current dept extensions. We need to strip them.
        
        dept_months = breakdown['dept_months']
        
        # Strip dept months from raw
        raw_without_dept = breakdown['raw_date'] - relativedelta(months=dept_months)
        date_with_subtenants_only = get_closest_end_of_month(raw_without_dept)
        
        # Calculate what the date would be WITHOUT subtenancies
        raw_no_sub_no_dept = raw_without_dept - timedelta(days=breakdown['sublet_days'])
        date_base_only = get_closest_end_of_month(raw_no_sub_no_dept)

        self.stdout.write("\n--- SUBTENANCY ANALYSIS ---")
        self.stdout.write(f"Confirmed Subtenant Days: {breakdown['sublet_days']}")
        self.stdout.write(f"1. Date (Base + Ext ONLY):        {date_base_only}")
        # Fixed: Replaced self.style.info with self.style.SUCCESS
        self.stdout.write(f"2. Date (Base + Ext + SUBTENANTS):{self.style.SUCCESS(str(date_with_subtenants_only))}")
        self.stdout.write(f"3. Current DB Date:               {current_db_date}")
        
        diff_days = (date_with_subtenants_only - current_db_date).days
        
        if date_with_subtenants_only == current_db_date:
            self.stdout.write(self.style.SUCCESS("\nMATCH FOUND: The current DB date matches (Base + Extensions + Subtenants)."))
            self.stdout.write("This suggests the DB is correct, but the 'New Calculated' result differs because of existing Department Extensions in the system.")
        elif date_base_only == current_db_date:
            self.stdout.write(self.style.WARNING("\nINSIGHT: The current DB date matches (Base + Extensions) IGNORING subtenants."))
            self.stdout.write("This suggests the old system failed to add subtenancy days.")
            self.stdout.write("Choosing [1] Accept NEW Date will fix this by adding the subtenancy days.")
        else:
            self.stdout.write(f"\nNo direct match. Discrepancy between Subtenancy-Calc and DB is {diff_days} days.")