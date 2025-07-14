from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db import transaction
from django.db.models import Max
from datetime import timedelta
import uuid

from ..permissions import GroupAndEmployeeTypePermission
from ..models import Tenant
from ..serializers import TenantSerializer, EngagementSerializer, NewTenantSerializer
from ..utils import ldap_utils, email_utils
from ..utils.helper import generate_secure_password
from .. import config as app_config

import logging

logger = logging.getLogger(__name__)

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def all_tenant_data_view(request):
    """
    API endpoint to retrieve tenant data, filterable by status (past, current, future).
    """
    #all_tenant_data_view.required_groups = ['Verwaltung']
    all_tenant_data_view.required_employee_types = ['DEPARTMENT']
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

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def create_new_tenant_view(request):
    """
    Handles the creation of a new tenant, including LDAP account and email notification.
    """
    create_new_tenant_view.required_groups = ['VERWALTUNG', 'ADMIN']
    create_new_tenant_view.required_employee_types = ['DEPARTMENT']

    serializer = NewTenantSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    # 1. Generate unique username and a secure password
    base_username = (data['name'][0] + data['surname']).lower().replace(' ', '').replace('ä','ae').replace('ö','oe').replace('ü','ue').replace('ß','ss')
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