import secrets
import string
from decimal import Decimal
import calendar
from datetime import timedelta, date
import uuid
import logging
import re

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from ..models import DepartmentSignature, Departure
from .. import config as app_config
from ..utils import email_utils

logger = logging.getLogger(__name__)


def checkValidSemesterFormat(semester: str) -> bool:
    """
    Check if the semester format is valid.
    Valid formats are 'SSYY' or 'WSYY/YY', where:
    - 'SS' is the summer semester (e.g., 'SS23' for Summer 2023)
    - 'WS' is the winter semester (e.g., 'WS23/24' for Winter 2023/2024)
    - 'YY' is the last two digits of the year (e.g., '23' for 2023)
    """
    if len(semester) == 4 and semester[:2] in ['SS'] and semester[2:].isdigit():
        return True
    elif len(semester) == 7 and semester[:2] == 'WS' and semester[2:4].isdigit() and semester[5:7].isdigit() and semester[4] == '/':
        # Check if second yy is after first yy
        first_year = int(semester[2:4])
        second_year = int(semester[5:7])
        if first_year + 1 == second_year:
            return True
    return False

def get_next_semester(current_semester: str, numbers: int = 1) -> str:
    """Calculates the next academic semester(s).
    
    Args:
        current_semester: The current semester string (e.g., 'SS23' or 'WS23/24')
        numbers: How many semesters to advance (default: 1)
    
    Returns:
        The semester string that is 'numbers' semesters after the current one.
    """
    if numbers < 1:
        logger.warning(f"Invalid numbers parameter: {numbers}. Must be >= 1.")
        return current_semester
    
    semester = current_semester
    for _ in range(numbers):
        ss_match = re.match(r'^SS(\d{2})$', semester)
        if ss_match:
            year = int(ss_match.group(1))
            next_year_short = (year + 1) % 100  # Handles year 99 -> 00 correctly
            semester = f"WS{year:02d}/{next_year_short:02d}"
            continue

        ws_match = re.match(r'^WS(\d{2})/(\d{2})$', semester)
        if ws_match:
            start_year = int(ws_match.group(1))
            next_year_short = (start_year + 1) % 100
            semester = f"SS{next_year_short:02d}"
            continue

        logger.warning(f"Could not determine next semester for unrecognized format: {semester}")
        return ""
    
    return semester

def get_previous_semester(current_semester: str, numbers: int = 1) -> str:
    """Calculates the previous academic semester(s).
    
    Args:
        current_semester: The current semester string (e.g., 'SS23' or 'WS23/24')
        numbers: How many semesters to go back (default: 1)
    
    Returns:
        The semester string that is 'numbers' semesters before the current one.
    """
    if numbers < 1:
        logger.warning(f"Invalid numbers parameter: {numbers}. Must be >= 1.")
        return current_semester
    
    semester = current_semester
    for _ in range(numbers):
        ss_match = re.match(r'^SS(\d{2})$', semester)
        if ss_match:
            year = int(ss_match.group(1))
            prev_year_short = (year - 1 + 100) % 100  # Handles year 00 correctly
            semester = f"WS{prev_year_short:02d}/{year:02d}"
            continue

        ws_match = re.match(r'^WS(\d{2})/(\d{2})$', semester)
        if ws_match:
            start_year = int(ws_match.group(1))
            semester = f"SS{start_year:02d}"
            continue

        logger.warning(f"Could not determine previous semester for unrecognized format: {semester}")
        return ""
    
    return semester

def semester_to_number(semester: str) -> int:
    """
    Converts a semester string to a numeric representation for easy comparison.
    'SSYY' -> YY * 2
    'WSYY/ZZ' -> YY * 2 + 1
    """
    ss_match = re.match(r'^SS(\d{2})$', semester)
    if ss_match:
        year = int(ss_match.group(1))
        return year * 2

    ws_match = re.match(r'^WS(\d{2})/(\d{2})$', semester)
    if ws_match:
        year = int(ws_match.group(1))
        return year * 2 + 1

    logger.warning(f"Could not convert unrecognized semester format to number: {semester}")
    return -1

def generate_secure_password(length=12):
    """Generates a secure, random password."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    # Ensure the password is complex enough, but for now, random choice is sufficient.
    password = ''.join(secrets.choice(alphabet) for i in range(length))
    return password

@transaction.atomic
def _ensure_signatures_for_all_confirmed_departures():
    """
    TEMPORARY MIGRATION FUNCTION.
    Checks all confirmed departures and creates missing signatures based on config.
    This ensures legacy data is consistent with the new signature creation logic.
    Can be removed after the migration phase is complete.
    """
    confirmed_departures = Departure.objects.select_related('tenant').filter(status='CONFIRMED')
    
    all_missing_signatures = []
    max_id_val = DepartmentSignature.objects.aggregate(max_id=Max('id'))['max_id'] or 0
    current_id = max_id_val + 1
    SENTINEL_DATE = date(1900, 1, 1)

    for departure in confirmed_departures:
        tenant = departure.tenant
        required_departments = set(app_config.DEPARTURE_SIGNATURE_ENGAGEMENTS)
        if tenant.current_floor:
            required_departments.add(tenant.current_floor)

        existing_signatures = set(
            DepartmentSignature.objects.filter(departure=departure).values_list('department_name', flat=True)
        )

        missing_departments = required_departments - existing_signatures

        if missing_departments:
            logger.info(f"Migration check: Found {len(missing_departments)} missing signatures for tenant {tenant.username}. Creating them now.")
            for dept_name in missing_departments:
                all_missing_signatures.append(
                    DepartmentSignature(
                        id=current_id,
                        departure=departure,
                        department_name=dept_name,
                        amount=Decimal('0.00'),
                        external_id=uuid.uuid4().hex,
                        signed_on=SENTINEL_DATE
                    )
                )
                current_id += 1

    if all_missing_signatures:
        DepartmentSignature.objects.bulk_create(all_missing_signatures)
        logger.info(f"Migration check: Successfully created a total of {len(all_missing_signatures)} missing signatures for legacy departures.")

@transaction.atomic
def create_and_notify_departure_signatures(departure):
    """
    Creates all required department signatures for a confirmed departure and notifies departments.
    """
    
    tenant = departure.tenant
    departments_to_sign = list(app_config.DEPARTURE_SIGNATURE_ENGAGEMENTS)

    # Add tenant's floor as a dynamic department for signature
    if tenant.current_floor:
        departments_to_sign.append(tenant.current_floor)
    else:
        logger.warning(f"Tenant {tenant.username} has no current_floor set. Cannot create floor signature for departure.")

    # Get the starting ID for new signatures
    max_id_val = DepartmentSignature.objects.aggregate(max_id=Max('id'))['max_id'] or 0
    SENTINEL_DATE = date(1900, 1, 1)
    
    new_signatures_to_create = []
    for i, dept_name in enumerate(departments_to_sign):
        new_signatures_to_create.append(
            DepartmentSignature(
                id=max_id_val + 1 + i,
                departure=departure,
                department_name=dept_name,
                amount=Decimal('0.00'),
                external_id=uuid.uuid4().hex,
                signed_on=SENTINEL_DATE
            )
        )
    
    if new_signatures_to_create:
        DepartmentSignature.objects.bulk_create(new_signatures_to_create)
        logger.info(f"Created {len(new_signatures_to_create)} signatures for departure of tenant {tenant.username}.")

    # Send email notifications
    email_context = {
        'name': f"{tenant.name} {tenant.surname}",
        'roomNumber': tenant.current_room or 'N/A',
    }

    for dept_name in departments_to_sign:
        dept_name_lower = dept_name.lower()
        if dept_name == tenant.current_floor:
            recipient_email = f"flur-{dept_name_lower}@schollheim.net"
        else:
            recipient_email = f"{dept_name_lower}@schollheim.net"
        
        email_utils.send_email_message(
            recipient_list=[recipient_email],
            subject=f"Auszug: {tenant.name} {tenant.surname}",
            html_template_name='email/department-departure-creation.html',
            context=email_context
        )
        logger.info(f"Sent departure signature notification to {recipient_email} for tenant {tenant.username}.")
        
    
    # --- TEMPORARY MIGRATION STEP ---
    # Since the old smartdorm handled signature creation a bit diffrent this function will ensure that every departure has a signature for every engagement
    # Will be removed (hopefully) when the new smartdorm is fully used, since then all departures should automatically have the required signatures
    _ensure_signatures_for_all_confirmed_departures()
    # --- END TEMPORARY MIGRATION STEP ---
    
def get_closest_end_of_month(target_date: date) -> date:
    """
    Finds the closest end-of-month date to the target_date.
    Example: 
    - Jan 28 -> Jan 31 (Closer to end of Jan than end of Dec)
    - Feb 02 -> Jan 31 (Closer to end of Jan than end of Feb)
    """
    # 1. End of the current month of the target_date
    last_day_current_month = calendar.monthrange(target_date.year, target_date.month)[1]
    eom_current = date(target_date.year, target_date.month, last_day_current_month)
    
    # 2. End of the previous month
    # Calculate first day of current month, subtract one day to get to prev month
    first_day_current = date(target_date.year, target_date.month, 1)
    eom_previous = first_day_current - timedelta(days=1)
    
    # Calculate differences
    diff_current = abs((eom_current - target_date).days)
    diff_previous = abs((eom_previous - target_date).days)
    
    if diff_previous < diff_current:
        return eom_previous
    return eom_current

def recalculate_tenant_contract_dates(tenant, dry_run=False) -> list:
    """
    Recalculates move_out and probation_end dates from scratch based on:
    1. Base contract duration
    2. Confirmed subtenants (adds duration)
    3. Approved extensions (adds fixed duration per extension)
    4. Rounds move_out to the closest end of month.
    """
    from ..models import Subtenant
    
    # Base Dates
    base_move_out = tenant.move_in + timedelta(days=app_config.DEFAULT_CONTRACT_DURATION_DAYS)
    base_probation = tenant.move_in + timedelta(days=app_config.PROBATION_PERIOD_DAYS)
    
    # Calculate confirmed subtenant duration
    confirmed_subtenants = Subtenant.objects.filter(
        tenant=tenant, 
        university_confirmation=True
    )
    
    total_sublet_days = 0
    for sub in confirmed_subtenants:
        # Ensure we don't calculate negative days if dates are messed up
        if sub.move_out > sub.move_in:
            duration = (sub.move_out - sub.move_in).days
            total_sublet_days += duration
            
    # Calculate extension duration
    extension_count = tenant.extension or 0
    total_extension_days = extension_count * app_config.DEFAULT_EXTENSION_DURATION_DAYS
    
    # Apply durations
    # Only update probation_end if it is in the future
    calculated_probation_end = tenant.probation_end
    if tenant.probation_end > timezone.now().date():
        calculated_probation_end = base_probation + timedelta(days=total_sublet_days)
        # Round probation_end to closest end of month
        calculated_probation_end = get_closest_end_of_month(calculated_probation_end)
    
    # Logic: Base + Sublet Days + Extension Days
    raw_move_out = base_move_out + timedelta(days=total_sublet_days + total_extension_days)
    
    # Round move_out to closest end of month
    final_move_out = get_closest_end_of_month(raw_move_out)

    
    # Apply changes if diff exists
    changes = []
    if tenant.probation_end != calculated_probation_end:
        #Only log if change is bigger than 3 days
        if abs((tenant.probation_end - calculated_probation_end).days) > 3:
            changes.append(f"Probation: {tenant.probation_end} -> {calculated_probation_end}")
        tenant.probation_end = calculated_probation_end
        
    if tenant.move_out != final_move_out:
        if abs((tenant.move_out - final_move_out).days) > 3:
            changes.append(f"MoveOut: {tenant.move_out} -> {final_move_out}")
        tenant.move_out = final_move_out
        
    if changes:
        if not dry_run:
            tenant.save()
            logger.info(f"Recalculated dates for {tenant.username}: {', '.join(changes)}")
            
    return changes