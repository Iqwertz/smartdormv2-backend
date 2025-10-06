from os import stat
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db import transaction
from django.db.models import Max, Q
from datetime import timedelta, date
import uuid
from django.shortcuts import get_object_or_404
from decimal import Decimal, InvalidOperation
from dateutil.relativedelta import relativedelta

from ..permissions import GroupAndEmployeeTypePermission
from ..models import Tenant, Subtenant, Rental, Room, DepartmentSignature, Departure, Claim
from ..serializers import TenantSerializer, NewTenantSerializer, SubtenantSerializer, NewSubtenantSerializer, RentalSerializer, TenantMoveSerializer, DepartmentSignatureSerializer, DepartureSerializer, DepartureDetailSerializer, ClaimSerializer
from ..utils import ldap_utils, email_utils, pdf_utils
from ..utils.helper import generate_secure_password, create_and_notify_departure_signatures
from .. import config as app_config

import logging

logger = logging.getLogger(__name__)

VERWALTUNG_ADMIN_GROUPS = ['VERWALTUNG', 'ADMIN']
DEPARTMENT_EMPLOYEE_TYPE = ['DEPARTMENT']

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def all_tenant_data_view(request):
    """
    API endpoint to retrieve tenant data, filterable by status (past, current, future).
    """
    all_tenant_data_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    all_tenant_data_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE
    # --- Filtering Logic ---
    status_filter = request.GET.get('status', 'current').lower()
    today = timezone.now().date()
    tenants = Tenant.objects.all()

    if status_filter == 'current':
        tenants = tenants.filter(
            move_in__lte=today,
            move_out__gte=today
        )
    elif status_filter == 'past':
        tenants = tenants.filter(
            move_out__lt=today
        )
    elif status_filter == 'future':
        tenants = tenants.filter(
            move_in__gt=today
        )
    elif status_filter == 'all':
        pass
    else:
        # If an invalid status is provided, default to 'current'
         tenants = tenants.filter(
            move_in__lte=today,
            move_out__gte=today
        )

    try:
        ordered_tenants = tenants.order_by('surname', 'name')
        serializer = TenantSerializer(ordered_tenants, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error retrieving tenant data: {e}")
        return Response(
            {"error": "An error occurred while retrieving tenant data."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def get_tenant_detail_view(request, tenant_id):
    get_tenant_detail_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    get_tenant_detail_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE
    
    tenant = get_object_or_404(Tenant, id=tenant_id)
    serializer = TenantSerializer(tenant)
    return Response(serializer.data)

@api_view(['PUT'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def update_tenant_view(request, tenant_id):
    update_tenant_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    update_tenant_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    tenant = get_object_or_404(Tenant, id=tenant_id)
    # Exclude non-editable fields from the request data before validation
    request.data.pop('current_room', None)
    request.data.pop('move_in', None)
    
    serializer = TenantSerializer(tenant, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def delete_tenant_view(request, tenant_id):
    delete_tenant_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    delete_tenant_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    tenant = get_object_or_404(Tenant, id=tenant_id)
    username_to_delete = tenant.username

    if not username_to_delete:
        # If there is no username, we can just delete the DB entry.
        tenant.delete()
        return Response({"message": "Tenant DB record deleted (no associated username)."}, status=status.HTTP_204_NO_CONTENT)

    # Proceed with LDAP and DB deletion
    try:
        ldap_utils.delete_ldap_user(username_to_delete)
        tenant.delete()
        logger.info(f"Successfully deleted tenant '{username_to_delete}' from DB and LDAP.")
        return Response({"message": f"Tenant '{username_to_delete}' was successfully deleted."}, status=status.HTTP_204_NO_CONTENT)
    except ConnectionError as e:
        logger.error(f"Failed to delete tenant '{username_to_delete}': {e}", exc_info=True)
        # The transaction will be rolled back, so the DB entry is not deleted if LDAP fails.
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.error(f"An unexpected error occurred while deleting tenant '{username_to_delete}': {e}", exc_info=True)
        return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_subtenants_for_tenant_view(request, tenant_id):
    list_subtenants_for_tenant_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    list_subtenants_for_tenant_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    subtenants = Subtenant.objects.filter(tenant_id=tenant_id).order_by('-move_in')
    serializer = SubtenantSerializer(subtenants, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_tenant_rentals_view(request, tenant_id):
    list_tenant_rentals_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    list_tenant_rentals_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    rentals = Rental.objects.filter(tenant_id=tenant_id).select_related('room').order_by('-move_in')
    serializer = RentalSerializer(rentals, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def move_tenant_view(request, tenant_id):
    move_tenant_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    move_tenant_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE
    
    serializer = TenantMoveSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    data = serializer.validated_data
    tenant = get_object_or_404(Tenant, id=tenant_id)
    new_room = get_object_or_404(Room, id=data['room_id'])
    move_date = data['move_date']

    # Find the current rental agreement to end it
    current_rental = Rental.objects.filter(tenant=tenant).order_by('-move_in').first()
    if not current_rental:
        return Response({"error": "No current rental found for this tenant."}, status=status.HTTP_404_NOT_FOUND)

    if move_date <= current_rental.move_in:
        return Response({"error": "Move date must be after the current move-in date."}, status=status.HTTP_400_BAD_REQUEST)
        
    # End the current rental one day before the new move
    current_rental.moved_out = move_date - timedelta(days=1)
    current_rental.save()

    # Create a new rental record for the new room
    max_id_result = Rental.objects.aggregate(max_id=Max('id'))
    new_id = (max_id_result['max_id'] or 0) + 1
    
    Rental.objects.create(
        id=new_id,
        external_id=uuid.uuid4().hex,
        tenant=tenant,
        room=new_room,
        move_in=move_date,
        moved_out=tenant.move_out  # Assume the contract end date remains the same
    )

    # Update the denormalized fields on the tenant model
    tenant.current_room = new_room.name
    tenant.current_floor = new_room.floor
    tenant.save()
    
    logger.info(f"Tenant {tenant.username} moved from room {current_rental.room.name} to {new_room.name} on {move_date}.")

    return Response(TenantSerializer(tenant).data, status=status.HTTP_200_OK)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def create_new_tenant_view(request):
    """
    Handles the creation of a new tenant, including LDAP account and email notification.
    """
    get_tenant_detail_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    get_tenant_detail_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    serializer = NewTenantSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    # 1. Generate unique username and a secure password
    base_username = (data['name'][0] + "." + data['surname']).lower().replace(' ', '').replace('ä','ae').replace('ö','oe').replace('ü','ue').replace('ß','ss')
    username = base_username
    counter = 1
    while Tenant.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1
    password = generate_secure_password()

    # 2. Create user in LDAP
    try:
        ldap_utils.create_ldap_user(
            username=username,
            password=password,
            first_name=data['name'],
            last_name=data['surname'],
            email=data['email'],
            group_dns=app_config.DEFAULT_TENANT_LDAP_GROUPS
        )
    except (ValueError, ConnectionError) as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # 3. Create Tenant in the database
    try:
        max_id_result = Tenant.objects.aggregate(max_id=Max('id'))
        new_id = (max_id_result['max_id'] or 0) + 1
        
        probation_end_date = data['move_in'] + timedelta(days=app_config.PROBATION_PERIOD_DAYS)
        move_out_date = data['move_in'] + timedelta(days=app_config.DEFAULT_CONTRACT_DURATION_DAYS)
        room = get_object_or_404(Room, name=data['current_room'])
        floor = room.floor
        
        tenant = Tenant.objects.create(
            id=new_id,
            external_id=uuid.uuid4().hex,
            username=username,
            name=data['name'],
            surname=data['surname'],
            email=data['email'],
            gender=data['gender'],
            nationality=data['nationality'],
            birthday=data['birthday'],
            tel_number=data.get('tel_number'),
            move_in=data['move_in'],
            move_out=move_out_date,
            probation_end=probation_end_date,
            current_room=data['current_room'],
            current_floor=floor,
            deposit=data['deposit'],
            university=data['university'],
            study_field=data['study_field'],
            note=data.get('note'),
            current_points=0,
            extension=0,
            sublet=0
        )

        # Create the initial rental record
        max_rental_id_result = Rental.objects.aggregate(max_id=Max('id'))
        new_rental_id = (max_rental_id_result['max_id'] or 0) + 1
        Rental.objects.create(
            id=new_rental_id,
            external_id=uuid.uuid4().hex,
            tenant=tenant,
            room=room,
            move_in=data['move_in'],
            moved_out=move_out_date
        )
    except Exception as e:
        logger.error(f"DB Error for new tenant '{username}': {e}. Attempting to revert LDAP user creation.", exc_info=True)
        try:
            ldap_utils.delete_ldap_user(username)
            logger.info(f"Successfully reverted LDAP creation for user '{username}'.")
        except Exception as ldap_e:
            logger.error(f"Failed to revert LDAP creation for user '{username}'. Manual cleanup required. Error: {ldap_e}", exc_info=True)
        
        return Response({"error": "Authentication entry was created, but failed to save tenant to database. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # 4. Send notification email to the new tenant
    email_context = {
        'greeting': data['name'],
        'username': username,
        'password': password,
    }
    email_sent = email_utils.send_email_message(
        recipient_list=[data['email']],
        subject="Dein SmartDorm Zugang",
        html_template_name='email/user-account-creation.html',
        context=email_context
    )
    
    if not email_sent:
        logger.warning(f"Tenant '{username}' created, but the welcome email to {data['email']} failed to send.")
        return Response(
            {"message": "Tenant created successfully, but the notification email could not be sent."},
            status=status.HTTP_201_CREATED
        )

    return Response(
        {"message": f"Tenant '{username}' created successfully and notification sent.", "username": username},
        status=status.HTTP_201_CREATED
    )
    
    
# --- Subtenant Views ---

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def create_subtenant_view(request):
    create_subtenant_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    create_subtenant_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    serializer = NewSubtenantSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    
    base_username = (data['name'] + " " + data['surname']).lower().replace(' ', '').replace('ä','ae').replace('ö','oe').replace('ü','ue').replace('ß','ss') # subtenant username format is diffrent from tenant to avoid conflicts
    username = base_username
    counter = 1
    #Log all Tenants with the same username, so we can increment it if needed
    logger.info(f"Creating subtenant with base username: {base_username}")
    
    while Tenant.objects.filter(username=username).exists():
        logger.info(f"Username {username} already exists, trying next increment.")
        username = f"{base_username}{counter}"
        counter += 1
        
    
    password = generate_secure_password()
    
    try:
        ldap_utils.create_ldap_user(
            username=username, password=password, first_name=data['name'],
            last_name=data['surname'], email=data['email'],
            group_dns=app_config.DEFAULT_SUBTENANT_LDAP_GROUPS
        )
    except (ValueError, ConnectionError) as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        max_id_result = Subtenant.objects.aggregate(max_id=Max('id'))
        new_id = (max_id_result['max_id'] or 0) + 1

        subtenant = Subtenant.objects.create(
            id=new_id, external_id=uuid.uuid4().hex, created_on=date.today(),
            name=data['name'], surname=data['surname'],
            email=data['email'], move_in=data['move_in'], move_out=data['move_out'],
            tenant_id=data['tenant_id'], room_id=data['room_id'],
            university_confirmation=data['university_confirmation']
        )
        
        # Update the main tenant's sublet count and adjust dates
        update_tenant_data_from_subtenant_change(subtenant)
            
    except Exception as e:
        logger.error(f"DB Error for new subtenant '{username}': {e}. Manual LDAP cleanup may be needed.", exc_info=True)
        return Response({"error": "Failed to save subtenant to database after creating auth entry."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    email_context = {
        'greeting': f"Hallo {data['name']}",
        'username': username, 'password': password,
    }
    email_sent = email_utils.send_email_message(
        recipient_list=[data['email']], subject="Dein SmartDorm Zugang als Untermieter",
        html_template_name='email/user-account-creation-subtenant.html',
        context=email_context
    )
    if not email_sent:
        logger.warning(f"Subtenant '{username}' created, but the welcome email failed to send.")

    return Response(SubtenantSerializer(subtenant).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_subtenants_view(request):
    list_subtenants_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    list_subtenants_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE
    
    status_filter = request.GET.get('status', 'current').lower()
    today = timezone.now().date()
    
    subtenants = Subtenant.objects.all()

    if status_filter == 'current':
        subtenants = subtenants.filter(
            move_in__lte=today,
            move_out__gte=today
        )
    elif status_filter == 'future':
        subtenants = subtenants.filter(
            move_in__gt=today
        )
    elif status_filter != 'all':
        # Default to current if status is invalid
        subtenants = subtenants.filter(
            move_in__lte=today,
            move_out__gte=today
        )

    ordered_subtenants = subtenants.select_related('tenant', 'room').order_by('-move_in', 'surname', 'name')
    
    serializer = SubtenantSerializer(ordered_subtenants, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def get_subtenant_detail_view(request, subtenant_id):
    get_subtenant_detail_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    get_subtenant_detail_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE
    
    subtenant = get_object_or_404(Subtenant, id=subtenant_id)
    serializer = SubtenantSerializer(subtenant)
    return Response(serializer.data)


@api_view(['PUT'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def update_subtenant_view(request, subtenant_id):
    update_subtenant_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    update_subtenant_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE
    
    subtenant = get_object_or_404(Subtenant, id=subtenant_id)
    # Use NewSubtenantSerializer to validate the subset of editable fields
    serializer = NewSubtenantSerializer(data=request.data, partial=True)
    if serializer.is_valid():
        data = serializer.validated_data
        for key, value in data.items():
            setattr(subtenant, key, value)
        subtenant.save()
        # Update the main tenant's sublet count and adjust dates if relevant fields changed
        update_tenant_data_from_subtenant_change(subtenant)
        return Response(SubtenantSerializer(subtenant).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

def update_tenant_data_from_subtenant_change(subtenant):
    """
    Updates the main tenant's sublet count and adjusts move_out and probation_end dates
    based on the current subtenants with university confirmation.
    """
    main_tenant = get_object_or_404(Tenant, id=subtenant.tenant_id)
    
    # Calculate the sublets and the sublet duration from all sublets of the tenant that have a university confirmation
    sublets = Subtenant.objects.filter(tenant_id=main_tenant.id, university_confirmation=True)
    main_tenant.sublet = sublets.count()
    sublet_duration = sum((s.move_out - s.move_in).days for s in sublets)
    
    # Update move_out and probation_end dates
    main_tenant.move_out += timedelta(days=sublet_duration)
    if main_tenant.probation_end > subtenant.move_in:
        main_tenant.probation_end += timedelta(days=sublet_duration)
    
    main_tenant.save()
    logger.info(f"Updated main tenant '{main_tenant.username}' sublet count to {main_tenant.sublet} and adjusted move_out to {main_tenant.move_out} due to subtenant change.")

@api_view(['DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def delete_subtenant_view(request, subtenant_id):
    delete_subtenant_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    delete_subtenant_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE
    
    subtenant = get_object_or_404(Subtenant, id=subtenant_id)
    #Reconstruct the username to delete, not the cleanest way since it assumes that the username isnt incremented when creating subtenants, however with the low amount of subtenants it is very unlikely to happen.
    username_to_delete = (subtenant.name + " " + subtenant.surname).lower().replace(' ', '').replace('ä','ae').replace('ö','oe').replace('ü','ue').replace('ß','ss'
                                                                                                                                                        )
    if not username_to_delete:
        subtenant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    try:
        ldap_utils.delete_ldap_user(username_to_delete)
        subtenant.delete()
        logger.info(f"Successfully deleted subtenant '{username_to_delete}' from DB and LDAP.")
        return Response(status=status.HTTP_204_NO_CONTENT)
    except ConnectionError as e:
        logger.error(f"Failed to delete subtenant '{username_to_delete}': {e}", exc_info=True)
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
# --- Department Signature Views ---
DEPARTMENT_CONFIG = {
    "tutoren": {"name": "TUTOREN", "group": "Tutoren"},
    "bar": {"name": "BAR", "group": "Barreferat"},
    "werk": {"name": "WERK", "group": "Werkreferat"},
    "innen": {"name": "INNEN", "group": "Innenreferat"},
    "finanzen": {"name": "FINANZEN", "group": "Finanzenreferat"},
    "h1eg": {"name": "H1EG", "group": "Flursprecher-H1EG"},
    "h1l1": {"name": "H1L1", "group": "Flursprecher-H1L1"},
    "h1l2": {"name": "H1L2", "group": "Flursprecher-H1L2"},
    "h1l3": {"name": "H1L3", "group": "Flursprecher-H1L3"},
    "h1l4": {"name": "H1L4", "group": "Flursprecher-H1L4"},
    "h1l5": {"name": "H1L5", "group": "Flursprecher-H1L5"},
    "h1r1": {"name": "H1R1", "group": "Flursprecher-H1R1"},
    "h1r2": {"name": "H1R2", "group": "Flursprecher-H1R2"},
    "h1r3": {"name": "H1R3", "group": "Flursprecher-H1R3"},
    "h1r4": {"name": "H1R4", "group": "Flursprecher-H1R4"},
    "h1r5": {"name": "H1R5", "group": "Flursprecher-H1R5"},
    "h2eg": {"name": "H2EG", "group": "Flursprecher-H2EG"},
    "h2f1": {"name": "H2F1", "group": "Flursprecher-H2F1"},
    "h2f2": {"name": "H2F2", "group": "Flursprecher-H2F2"},
    "h2f3": {"name": "H2F3", "group": "Flursprecher-H2F3"},
    "h2f4": {"name": "H2F4", "group": "Flursprecher-H2F4"},
    "h2f5": {"name": "H2F5", "group": "Flursprecher-H2F5"},
}

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_department_signatures_view(request, department_slug):
    """
    Lists departure signatures for a specific department.
    Filters by signed status based on a query parameter.
    - `?signed=false` (default): Shows unsigned signatures for 'CONFIRMED' departures.
    - `?signed=true`: Shows all signed signatures.
    """
    if department_slug not in DEPARTMENT_CONFIG:
        return Response({"error": "Invalid department specified."}, status=status.HTTP_404_NOT_FOUND)

    config = DEPARTMENT_CONFIG[department_slug]
    list_department_signatures_view.required_groups = [config["group"], 'ADMIN']

    if not GroupAndEmployeeTypePermission().has_permission(request, list_department_signatures_view):
        return Response({"detail": "You do not have permission to perform this action."}, status=status.HTTP_403_FORBIDDEN)

    signed_status = request.query_params.get('signed', 'false').lower() == 'true'
    SENTINEL_DATE = date(1900, 1, 1)

    if signed_status:
        queryset = DepartmentSignature.objects.select_related('departure', 'departure__tenant').filter(
            department_name=config["name"],
            signed_on__gt=SENTINEL_DATE,
            departure__status='CONFIRMED'
        ).order_by('-signed_on')
    else:
        queryset = DepartmentSignature.objects.select_related('departure', 'departure__tenant').filter(
            department_name=config["name"],
            signed_on=SENTINEL_DATE,
            departure__status='CONFIRMED'
        ).order_by('departure__tenant__surname', 'departure__tenant__name')

    final_queryset = queryset.distinct()

    serializer = DepartmentSignatureSerializer(final_queryset, many=True)
    return Response(serializer.data)


@api_view(['PUT'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def update_department_signature_view(request, signature_id):
    """
    Updates a department signature, setting the amount and signing it if not already signed.
    """
    signature = get_object_or_404(DepartmentSignature.objects.select_related('departure'), id=signature_id)
    
    department_slug = next((slug for slug, conf in DEPARTMENT_CONFIG.items() if conf["name"] == signature.department_name), None)
    
    if not department_slug:
        return Response({"error": "Signature belongs to an unknown department."}, status=status.HTTP_400_BAD_REQUEST)

    config = DEPARTMENT_CONFIG[department_slug]
    update_department_signature_view.required_groups = [config["group"], 'ADMIN']

    if not GroupAndEmployeeTypePermission().has_permission(request, update_department_signature_view):
        return Response({"detail": "You do not have permission to perform this action."}, status=status.HTTP_403_FORBIDDEN)

    if signature.departure.status == 'CLOSED':
        return Response({"error": "Cannot update signature for a closed departure."}, status=status.HTTP_403_FORBIDDEN)

    amount_str = request.data.get('amount')
    if amount_str is None:
        return Response({"error": "Amount is required."}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        signature.amount = Decimal(amount_str)
    except (TypeError, InvalidOperation):
        return Response({"error": "Invalid amount format."}, status=status.HTTP_400_BAD_REQUEST)

    # If the signature has the sentinel date, update it to today's date to "sign" it.
    SENTINEL_DATE = date(1900, 1, 1)
    if signature.signed_on == SENTINEL_DATE:
        signature.signed_on = timezone.now().date()
    
    signature.save()
    
    #Send email to tenant depending on amount of debt
    if signature.amount > Decimal('0.00'):
        email_utils.send_email_message(
            recipient_list=[signature.departure.tenant.email],
            subject=f'Schulden: {config["group"]}',
            html_template_name='email/tenant-departure-update-debt.html',
            context={
                'greeting': signature.departure.tenant.name,
                'amount': signature.amount,
                'departmentName': config["group"]
            }
        )
    else:
        email_utils.send_email_message(
            recipient_list=[signature.departure.tenant.email],
            subject=f'Keine Schulden: {config["group"]}',
            html_template_name='email/tenant-departure-update.html',
            context={
                'greeting': signature.departure.tenant.name,
                'departmentName': config["group"]
            }
        )
    
    serializer = DepartmentSignatureSerializer(signature)
    return Response(serializer.data, status=status.HTTP_200_OK)


# --- Departure Views ---

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_departure_candidates_view(request):
    list_departure_candidates_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    list_departure_candidates_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    today = timezone.now().date()
    eight_months_from_now = today + relativedelta(months=8)

    # Find tenants whose contracts end within 8 months but are not yet past
    # and who do not already have a departure record. #Todo the move out threshold should be configurable in the config.py
    candidates = Tenant.objects.filter(
        move_out__lte=eight_months_from_now,
        move_out__gte=today,
        departure__isnull=True  # Exclude tenants with existing departure records
    ).order_by('move_out')

    serializer = TenantSerializer(candidates, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def create_departure_view(request):
    create_departure_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    create_departure_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    tenant_id = request.data.get('tenant_id')
    if not tenant_id:
        return Response({"error": "Tenant ID is required."}, status=status.HTTP_400_BAD_REQUEST)

    tenant = get_object_or_404(Tenant, id=tenant_id)
    if Departure.objects.filter(tenant=tenant).exists():
        return Response({"error": "Departure request for this tenant already exists."}, status=status.HTTP_409_CONFLICT)

    departure = Departure.objects.create(
        tenant=tenant,
        external_id=uuid.uuid4().hex,
        created_on=timezone.now().date(),
        status=Departure.Status.CREATED
    )
    serializer = DepartureSerializer(departure)
    
    pdf_data = {
        'Bewohnername': tenant.name + " " + tenant.surname,
        'Wohnzeitende': tenant.move_out.strftime('%d.%m.%Y'),
        'Zimmernummer Bewohner': tenant.current_room or "N/A",
    }

    #Send email to tenant
    email_utils.send_email_message(
        recipient_list=[tenant.email],
        subject="Deine Wohnzeit läuft bald aus",
        html_template_name='email/tenant-departure-creation.html',
        context={
            'greeting': tenant.name,
            'departureDate': tenant.move_out.strftime('%d.%m.%Y'),
        },
        dynamic_pdf_template_path='pdf/Wohnzeitende-Mitteilung.pdf',
        dynamic_pdf_data=pdf_data,
        dynamic_pdf_filename=f"Wohnzeitende-Mitteilung_{tenant.surname}.pdf"
    )
    
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_departures_view(request):
    list_departures_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    list_departures_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    status_filter = request.query_params.get('status', '').upper()
    valid_statuses = [s.name for s in Departure.Status]
    if status_filter not in valid_statuses:
        return Response({"error": f"Invalid status. Valid options are: {', '.join(valid_statuses)}"}, status=status.HTTP_400_BAD_REQUEST)

    departures = Departure.objects.filter(status=status_filter).select_related('tenant')

    if status_filter == Departure.Status.CONFIRMED:
        # For confirmed, we need signatures, so prefetch them
        departures = departures.prefetch_related('departmentsignature_set')
        serializer = DepartureDetailSerializer(departures, many=True)
    else:
        serializer = DepartureSerializer(departures, many=True)

    return Response(serializer.data)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def send_departure_reminder_view(request, departure_id):
    send_departure_reminder_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    send_departure_reminder_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    departure = get_object_or_404(Departure.objects.select_related('tenant'), tenant_id=departure_id)
    if departure.status != Departure.Status.CREATED:
        return Response({"error": "Can only send reminders for open departure requests."}, status=status.HTTP_400_BAD_REQUEST)

    pdf_data = {
        'Bewohnername': departure.tenant.name + " " + departure.tenant.surname,
        'Wohnzeitende': departure.tenant.move_out.strftime('%d.%m.%Y'),
        'Zimmernummer Bewohner': departure.tenant.current_room or "N/A",
    }

    #Send email to tenant
    email_sent = email_utils.send_email_message(
        recipient_list=[departure.tenant.email],
        subject="Erinnerung: Deine Wohnzeit läuft bald aus",
        html_template_name='email/tenant-departure-creation.html',
        context={
            'greeting': departure.tenant.name,
            'departureDate': departure.tenant.move_out.strftime('%d.%m.%Y'),
        },
        dynamic_pdf_template_path='pdf/Wohnzeitende-Mitteilung.pdf',
        dynamic_pdf_data=pdf_data,
        dynamic_pdf_filename=f"Wohnzeitende-Mitteilung_{departure.tenant.surname}.pdf"
    )

    if email_sent:
        return Response({"message": "Reminder email sent successfully."}, status=status.HTTP_200_OK)
    else:
        return Response({"error": "Failed to send reminder email."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def close_departure_view(request, departure_id):
    close_departure_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    close_departure_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    departure = get_object_or_404(Departure.objects.select_related('tenant'), tenant_id=departure_id)
    if departure.status != Departure.Status.CONFIRMED:
        return Response({"error": "Departure must be confirmed to be closed."}, status=status.HTTP_400_BAD_REQUEST)

    # Check if all signatures are done
    SENTINEL_DATE = date(1900, 1, 1)
    unsigned_count = DepartmentSignature.objects.filter(
        departure=departure,
        signed_on=SENTINEL_DATE
    ).count()

    if unsigned_count > 0:
        return Response({"error": f"{unsigned_count} department signature(s) are still missing."}, status=status.HTTP_400_BAD_REQUEST)

    # Update tenant's move_out date if provided
    new_move_out_date_str = request.data.get('move_out_date')
    if new_move_out_date_str:
        try:
            new_move_out_date = date.fromisoformat(new_move_out_date_str)
            tenant = departure.tenant
            tenant.move_out = new_move_out_date
            tenant.save()
        except (ValueError, TypeError):
            return Response({"error": "Invalid date format for move_out_date. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

    departure.status = Departure.Status.CLOSED
    departure.save()
    
    #Send email to tenant
    email_utils.send_email_message(
        recipient_list=[departure.tenant.email],
        subject="Dein Auszug aus dem Schollheim",
        html_template_name='email/tenant-departure-approval.html',
        context={
            'greeting': departure.tenant.name,
            'departureDate': departure.tenant.move_out.strftime('%d.%m.%Y')
        }
    )

    return Response({"message": "Departure successfully closed."}, status=status.HTTP_200_OK)


# --- Claim (Extension) Views ---

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_claims_view(request):
    list_claims_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    list_claims_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    status_filter = request.query_params.get('status', '').upper()
    
    if status_filter == 'COMPLETED':
        queryset = Claim.objects.filter(
            Q(status=Claim.Status.APPROVED) | Q(status=Claim.Status.REJECTED)
        ).select_related('tenant').order_by('-created_on')
    else:
        valid_statuses = [s.name for s in Claim.Status]
        if status_filter not in valid_statuses:
            return Response({"error": f"Invalid status. Valid options are: {', '.join(valid_statuses)} or COMPLETED"}, status=status.HTTP_400_BAD_REQUEST)
        queryset = Claim.objects.filter(status=status_filter).select_related('tenant').order_by('created_on')

    serializer = ClaimSerializer(queryset, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def send_claim_reminder_view(request, claim_id):
    send_claim_reminder_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    send_claim_reminder_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    claim = get_object_or_404(Claim.objects.select_related('tenant'), id=claim_id)
    if claim.status != Claim.Status.CREATED:
        return Response({"error": "Can only send reminders for open claims."}, status=status.HTTP_400_BAD_REQUEST)

    tenant = claim.tenant

    pdf_data = pdf_utils.prepare_extension_application_pdf_data(tenant)
    
    email_sent = email_utils.send_email_message(
        recipient_list=[claim.tenant.email],
        subject="Erinnerung: Dein Antrag auf Wohnzeitverlängerung",
        html_template_name='email/tenant-extension-reminder.html',
        context={
            'greeting': claim.tenant.name,
            'departureDateMinus3Months': (claim.tenant.move_out - timedelta(days=90)).strftime('%d.%m.%Y'),
            'departureDate': claim.tenant.move_out.strftime('%d.%m.%Y'),
        },
        dynamic_pdf_template_path='pdf/Wohnzeitverlaengerung-Bewerbungsformular.pdf',
        dynamic_pdf_data=pdf_data,
        dynamic_pdf_filename=f"Antrag_Wohnzeitverlaengerung_{tenant.surname}.pdf"
    )

    if email_sent:
        return Response({"message": "Reminder email with application form sent successfully."}, status=status.HTTP_200_OK)
    return Response({"error": "Failed to send reminder email."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def update_claim_status_view(request, claim_id):
    update_claim_status_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    update_claim_status_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    claim = get_object_or_404(Claim, id=claim_id)
    new_status = request.data.get('status', '').upper()

    if claim.status == Claim.Status.CREATED and new_status == Claim.Status.PROCESSING:
        claim.status = Claim.Status.PROCESSING
        claim.save()
        serializer = ClaimSerializer(claim)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    return Response({"error": f"Invalid status transition from {claim.status} to {new_status}."}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def process_claim_decision_view(request, claim_id):
    process_claim_decision_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    process_claim_decision_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    claim = get_object_or_404(Claim.objects.select_related('tenant'), id=claim_id)
    if claim.status != Claim.Status.PROCESSING:
        return Response({"error": "Claim is not in 'PROCESSING' state."}, status=status.HTTP_400_BAD_REQUEST)

    decision = request.data.get('decision', '').upper()
    tenant = claim.tenant

    if decision == 'REJECTED':
        claim.status = Claim.Status.REJECTED
        claim.save()
        # Find the postponed departure and set it to confirmed
        departure = get_object_or_404(Departure, tenant=tenant, status=Departure.Status.POSTPONED)
        departure.status = Departure.Status.CONFIRMED
        departure.save()
        
        # Create signatures and notify departments
        create_and_notify_departure_signatures(departure)
        
        #Send email to tenant
        email_utils.send_email_message(
            recipient_list=[tenant.email],
            subject="Dein Antrag auf Wohnzeitverlängerung wurde abgelehnt",
            html_template_name='email/tenant-extension-rejection.html',
            context={
                'greeting': tenant.name,
                'departureDate': tenant.move_out.strftime('%d.%m.%Y'),
                'departureDate1': (tenant.move_out + timedelta(days=30)).strftime('%d.%m.%Y'),
                'departureDate2': (tenant.move_out + timedelta(days=60)).strftime('%d.%m.%Y')
            }
        )
        
        return Response({"message": "Claim rejected and departure confirmed."}, status=status.HTTP_200_OK)

    elif decision == 'APPROVED':
        claim.status = Claim.Status.APPROVED
        claim.save()
        
        tenant.extension = (tenant.extension or 0) + 1
        
        new_move_out_date_str = request.data.get('move_out_date')
        if new_move_out_date_str:
            try:
                tenant.move_out = date.fromisoformat(new_move_out_date_str)
            except (ValueError, TypeError):
                return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            tenant.move_out += timedelta(days=app_config.DEFAULT_EXTENSION_DURATION_DAYS)
        
        tenant.save()
        Departure.objects.filter(tenant=tenant).delete()
        
        #Send email to tenant
        email_utils.send_email_message(
            recipient_list=[tenant.email],
            subject="Deine Wohnzeitverlängerung wurde genehmigt",
            html_template_name='email/tenant-extension-approval.html',
            context={
                'greeting': tenant.name,
                'departureDate': tenant.move_out.strftime('%d.%m.%Y'),
            }
        )
        
        return Response({"message": "Claim approved, tenant extended, and departure deleted."}, status=status.HTTP_200_OK)

    return Response({"error": "Invalid decision. Must be 'APPROVED' or 'REJECTED'."}, status=status.HTTP_400_BAD_REQUEST)