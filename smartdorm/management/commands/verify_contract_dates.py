from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from smartdorm.models import Tenant
from smartdorm.utils.helper import recalculate_tenant_contract_dates

class Command(BaseCommand):
    help = 'Recalculates contract end dates and probation periods for active tenants based on extensions and subtenants.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually apply the calculated changes to the database. Without this, the script runs in read-only mode.',
        )
        parser.add_argument(
            '--tenant',
            type=str,
            help='Run for a specific tenant username only.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        specific_tenant = options['tenant']
        
        mode_str = "LIVE UPDATE" if apply_changes else "DRY RUN (Read-Only)"
        color_style = self.style.SUCCESS if apply_changes else self.style.WARNING
        
        self.stdout.write(color_style(f"Starting Contract Date Verification - Mode: {mode_str}"))

        today = timezone.now().date()
        
        # Filter for tenants who haven't moved out yet (Current and Future)
        tenants = Tenant.objects.filter(move_out__gte=today)
        
        if specific_tenant:
            tenants = tenants.filter(username=specific_tenant)

        total_tenants = tenants.count()
        changed_tenants = 0
        total_changes = 0

        self.stdout.write(f"Checking {total_tenants} tenants...\n")

        for tenant in tenants:
            try:
                # We assume you updated the helper function to accept dry_run and return changes
                # based on Step 1.
                changes = recalculate_tenant_contract_dates(tenant, dry_run=not apply_changes)
                
                if changes:
                    changed_tenants += 1
                    total_changes += len(changes)
                    
                    self.stdout.write(self.style.MIGRATE_HEADING(f"Tenant: {tenant.name} {tenant.surname} ({tenant.username})"))
                    for change in changes:
                        self.stdout.write(f"  - {change}")
                    self.stdout.write("") # Newline
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing {tenant.username}: {str(e)}"))

        # Summary
        self.stdout.write(self.style.SUCCESS("-" * 30))
        self.stdout.write(f"Finished processing {total_tenants} tenants.")
        
        if changed_tenants == 0:
            self.stdout.write(self.style.SUCCESS("No discrepancies found. All dates are correct."))
        else:
            if apply_changes:
                self.stdout.write(self.style.SUCCESS(f"Updated {changed_tenants} tenants with {total_changes} modifications."))
            else:
                self.stdout.write(self.style.WARNING(f"Found {changed_tenants} tenants that require updates."))
                self.stdout.write(self.style.WARNING("Run with '--apply' to execute these changes."))