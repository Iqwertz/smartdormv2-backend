from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db import transaction
from django.db.models import Max
from datetime import timedelta, date
import uuid
from django.shortcuts import get_object_or_404


from ..permissions import GroupAndEmployeeTypePermission
from ..models import Tenant, Subtenant, Rental, Room, Departure, DepartmentSignature
from ..serializers import (
    TenantSerializer, EngagementSerializer, NewTenantSerializer, 
    SubtenantSerializer, NewSubtenantSerializer, RentalSerializer, 
    TenantMoveSerializer, DepartureSerializer, SignSignatureSerializer, DepartmentSignatureSerializer
)
from ..utils import ldap_utils, email_utils
from ..utils.helper import generate_secure_password
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
        floor = data['current_room'][0] if data['current_room'] and data['current_room'][0].isdigit() else None
        
        Tenant.objects.create(
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
    except Exception as e:
        logger.error(f"DB Error for new tenant '{username}': {e}. Manual LDAP cleanup may be needed.", exc_info=True) #Maybe revert LDAP creation here? #todo
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
        return Response(SubtenantSerializer(subtenant).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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

# --- Departure Views ---

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_departure_candidates_view(request):
    list_departure_candidates_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    list_departure_candidates_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE
    
    today = timezone.now().date()
    threshold_date = today + timedelta(days=app_config.DEPARTURE_CANDIDATE_TIMEFRAME_DAYS)
    existing_departure_tenant_ids = Departure.objects.values_list('tenant_id', flat=True)
    candidates = Tenant.objects.filter(
        move_out__gte=today,
        move_out__lte=threshold_date
    ).exclude(
        id__in=existing_departure_tenant_ids
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
        return Response({"error": "tenant_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    tenant = get_object_or_404(Tenant, id=tenant_id)
    if Departure.objects.filter(tenant=tenant).exists():
        return Response({"error": "Departure record already exists for this tenant."}, status=status.HTTP_400_BAD_REQUEST)

    departure = Departure.objects.create(
        tenant=tenant,
        created_on=timezone.now().date(),
        external_id=uuid.uuid4().hex,
        status='PENDING'
    )
    
    max_sig_id_result = DepartmentSignature.objects.aggregate(max_id=Max('id'))
    current_sig_id = (max_sig_id_result['max_id'] or 0)
    for dept_name in app_config.DEPARTURE_SIGNATURE_DEPARTMENTS:
        current_sig_id += 1
        DepartmentSignature.objects.create(
            id=current_sig_id,
            departure=departure,
            department_name=dept_name,
            amount=0.00,
            signed_on=None,
            external_id=uuid.uuid4().hex
        )
    serializer = DepartureSerializer(departure)
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_departures_view(request):
    list_departures_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    list_departures_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE
    
    status_filter = request.GET.get('status', 'CREATED').upper()
    if status_filter not in ['POSTPONED', 'CREATED', 'CLOSED', 'CONFIRMED']:
        status_filter = 'CREATED'
        
    #Print status of all departures for debugging
    logger.info(f"Listing all status values that appear in Departures: {Departure.objects.values_list('status', flat=True).distinct()}")
        
    departures = Departure.objects.filter(status=status_filter).select_related('tenant').prefetch_related('signatures').order_by('tenant__move_out')
    serializer = DepartureSerializer(departures, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_departures_for_signing_view(request):
    list_departures_for_signing_view.required_groups = app_config.DEPARTURE_SIGNATURE_DEPARTMENTS
    list_departures_for_signing_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE

    user_groups = [group.name for group in request.user.groups.all()]
    departures_to_sign = Departure.objects.filter(
        status='CREATED',
        signatures__department_name__in=user_groups,
        signatures__signed_on__isnull=True
    ).distinct().select_related('tenant').prefetch_related('signatures').order_by('tenant__move_out')
    serializer = DepartureSerializer(departures_to_sign, many=True)
    return Response(serializer.data)

@api_view(['PUT'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def sign_departure_signature_view(request, signature_id):
    sign_departure_signature_view.required_groups = app_config.DEPARTURE_SIGNATURE_DEPARTMENTS + VERWALTUNG_ADMIN_GROUPS
    sign_departure_signature_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE
    
    signature = get_object_or_404(DepartmentSignature, id=signature_id)
    user_groups = [group.name for group in request.user.groups.all()]
    if not any(g in user_groups for g in [signature.department_name] + VERWALTUNG_ADMIN_GROUPS):
        return Response({"error": "You do not have permission to sign for this department."}, status=status.HTTP_403_FORBIDDEN)
        
    serializer = SignSignatureSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    signature.amount = serializer.validated_data['amount']
    signature.signed_on = timezone.now().date()
    signature.save()
    return Response(DepartmentSignatureSerializer(signature).data, status=status.HTTP_200_OK)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def close_departure_view(request, tenant_id):
    close_departure_view.required_groups = VERWALTUNG_ADMIN_GROUPS
    close_departure_view.required_employee_types = DEPARTMENT_EMPLOYEE_TYPE
    
    departure = get_object_or_404(Departure.objects.prefetch_related('signatures'), tenant_id=tenant_id)
    if not all(sig.signed_on is not None for sig in departure.signatures.all()):
        return Response({"error": "Cannot close departure. Not all departments have signed off."}, status=status.HTTP_400_BAD_REQUEST)
        
    departure.status = 'CLOSED'
    departure.save()
    return Response(DepartureSerializer(departure).data, status=status.HTTP_200_OK)