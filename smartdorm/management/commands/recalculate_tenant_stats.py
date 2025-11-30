from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import logging

from smartdorm.models import Tenant

# Configure logging
logger = logging.getLogger('smartdorm')

class Command(BaseCommand):
    help = 'Recalculates points, sublet duration (months), and extensions for current tenants.'

    def handle(self, *args, **options):
        self.stdout.write("Starting nightly tenant statistics recalculation...")
        logger.info("Starting nightly tenant statistics recalculation.")

        today = timezone.now().date()

        # Filter only tenants currently living in the dorm
        tenants = Tenant.objects.filter(
            move_in__lte=today,
            move_out__gte=today
        ).prefetch_related(
            'engagement_set',
            'subtenant_set',
            'claim_set'
        )

        updates_count = 0

        # Process tenants in a single atomic transaction
        with transaction.atomic():
            for tenant in tenants:
                changes = []

                # --- Recalculate Points ---
                # Sum points from all engagements where compensate=True
                calculated_points = Decimal('0.00')
                compensated_engagements = [e for e in tenant.engagement_set.all() if e.compensate]
                for eng in compensated_engagements:
                    calculated_points += eng.points

                current_points = tenant.current_points if tenant.current_points is not None else Decimal('0.00')
                
                if current_points != calculated_points:
                    changes.append(f"Points: {current_points} -> {calculated_points}")
                    tenant.current_points = calculated_points

                # --- Recalculate Sublet Duration ---
                calculated_sublet_months = 0.0
                confirmed_subtenants = [s for s in tenant.subtenant_set.all()] #if s.university_confirmation]
                
                total_sublet_days = 0
                for sub in confirmed_subtenants:
                    if sub.move_out and sub.move_in:
                        duration = (sub.move_out - sub.move_in).days
                        if duration > 0:
                            total_sublet_days += duration

                if total_sublet_days > 0:
                    # Convert days to months (Approximation: 30 days = 1 month)
                    raw_months = total_sublet_days / 30.0
                    # Round to nearest 0.5
                    calculated_sublet_months = round(raw_months * 2) / 2
                
                current_sublet = tenant.sublet if tenant.sublet is not None else 0.0
                
                if current_sublet != calculated_sublet_months:
                    changes.append(f"Sublet: {current_sublet} -> {calculated_sublet_months} ({total_sublet_days} days)")
                    tenant.sublet = calculated_sublet_months

                # --- Recalculate Extensions ---
                # Count claims where status is APPROVED and type is EXTENSION
                approved_claims = [c for c in tenant.claim_set.all() if c.status == 'APPROVED' and c.type == 'EXTENSION']
                calculated_extensions = len(approved_claims)

                current_extension = tenant.extension if tenant.extension is not None else 0
                
                if current_extension != calculated_extensions:
                    changes.append(f"Extensions: {current_extension} -> {calculated_extensions}")
                    tenant.extension = calculated_extensions

                if changes:
                    #tenant.save(update_fields=['current_points', 'sublet', 'extension'])
                    updates_count += 1
                    
                    log_msg = f"Updated Tenant {tenant.username}: {', '.join(changes)}"
                    self.stdout.write(self.style.WARNING(log_msg))
                    logger.info(log_msg)

        success_msg = f"Recalculation complete. {updates_count} tenants updated."
        self.stdout.write(self.style.SUCCESS(success_msg))
        logger.info(success_msg)