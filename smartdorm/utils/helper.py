import secrets
import string
from decimal import Decimal
from datetime import date
import uuid
import logging

from django.db import transaction
from django.db.models import Max

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