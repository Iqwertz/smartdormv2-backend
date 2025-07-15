import uuid
from django.utils import timezone
from django.db import transaction
from django.db.models import Max, Q
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status

from ..models import Tenant, Subtenant, Parcel, Room
from ..serializers import ParcelSerializer, ParcelCreateRequestSerializer
from ..permissions import GroupAndEmployeeTypePermission
from ..utils.email_utils import send_email_message

import logging
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def get_next_parcel_id():
    """Generates the next available ID for the Parcel model."""
    max_id = Parcel.objects.aggregate(max_id=Max('id'))['max_id']
    return (max_id or 0) + 1

def find_current_tenant_by_room(room_name):
    today = timezone.now().date()
    try:
        return Tenant.objects.get(
            current_room__iexact=room_name,
            move_in__lte=today,
            move_out__gte=today
        )
    except Tenant.DoesNotExist:
        return None
    except Tenant.MultipleObjectsReturned:
        logger.warning(f"Multiple current tenants found for room '{room_name}'. This should not happen.")
        raise ValueError(f"Room name '{room_name}' is not unique for current tenants.")


def find_current_tenants_by_name(name, surname):
    today = timezone.now().date()
    return Tenant.objects.filter(
        name__iexact=name,
        surname__iexact=surname,
        move_in__lte=today,
        move_out__gte=today
    )

def find_current_subtenants_by_name(name, surname):
    today = timezone.now().date()
    return Subtenant.objects.filter(
        name__iexact=name,
        surname__iexact=surname,
        move_in__lte=today,
        move_out__gte=today
    )

# --- API Views ---
@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic # Ensure parcel creation and ID generation are atomic
def create_parcel_view(request):
    """
    Creates a parcel for a tenant or subtenant and notifies them.
    """
    create_parcel_view.required_groups = ['ADMIN', 'Verwaltung']
    # create_parcel_view.required_employee_types = ['DEPARTMENT']

    request_serializer = ParcelCreateRequestSerializer(data=request.data)
    if not request_serializer.is_valid():
        return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = request_serializer.validated_data
    room_str = data.get('room')
    name_str = data.get('name')
    surname_str = data.get('surname')
    quantity = data['quantity']
    registered = data['registered']

    recipient_tenant = None
    recipient_subtenant = None
    recipient_email = None
    recipient_name_for_greeting = "Bewohner/in"

    try:
        if room_str:
            recipient_tenant = find_current_tenant_by_room(room_str)
            if not recipient_tenant:
                return Response({"error": f"No current tenant found for room '{room_str}'."}, status=status.HTTP_404_NOT_FOUND)
        elif name_str and surname_str:
            tenants = find_current_tenants_by_name(name_str, surname_str)
            if tenants.count() == 1:
                recipient_tenant = tenants.first()
            elif tenants.count() > 1:
                return Response({"error": f"Name '{name_str} {surname_str}' is not unique for current tenants. Please use room number."}, status=status.HTTP_400_BAD_REQUEST)
            else: # No tenant found, look for subtenant
                subtenants = find_current_subtenants_by_name(name_str, surname_str)
                if subtenants.count() == 1:
                    recipient_subtenant = subtenants.first()
                elif subtenants.count() > 1:
                    return Response({"error": f"Name '{name_str} {surname_str}' is not unique for current subtenants. Please clarify."}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    return Response({"error": f"No current tenant or subtenant found with name '{name_str} {surname_str}'."}, status=status.HTTP_404_NOT_FOUND)
        else:
            # This case should be caught by serializer validation, but as a safeguard:
            return Response({"error": "Insufficient information to identify recipient."}, status=status.HTTP_400_BAD_REQUEST)

        # Determine recipient details for email
        if recipient_tenant:
            recipient_email = recipient_tenant.email
            recipient_name_for_greeting = f"{recipient_tenant.name}"
        elif recipient_subtenant:
            recipient_email = recipient_subtenant.email
            recipient_name_for_greeting = f"{recipient_subtenant.name} {recipient_subtenant.surname}"

        if not recipient_email:
            logger.error(f"No email address found for recipient. Parcel for {recipient_name_for_greeting if (recipient_tenant or recipient_subtenant) else 'unknown'}")


        # Create Parcel object
        parcel = Parcel(
            id=get_next_parcel_id(),
            external_id=uuid.uuid4().hex,
            tenant=recipient_tenant,
            subtenant=recipient_subtenant,
            count=quantity,
            registered=registered,
            arrived=timezone.now(),
            picked_up=None
        )
        parcel.save()
        logger.info(f"Parcel {parcel.external_id} created for {recipient_name_for_greeting or 'Unknown'}")

        # Send email notification
        if recipient_email:
            email_subject = "Benachrichtigung: Post für Dich"
            if registered:
                count_message = "ist ein Einschreiben"
                actual_quantity_for_email = 1
            elif quantity == 1:
                count_message = "ist ein Paket"
                actual_quantity_for_email = 1
            else:
                count_message = f"sind {quantity} Pakete"
                actual_quantity_for_email = quantity

            email_context = {
                'recipient_name': recipient_name_for_greeting,
                'count_message': count_message,
                'quantity': actual_quantity_for_email,
            }
            send_email_message(
                recipient_list=[recipient_email],
                subject=email_subject,
                html_template_name='email/tenant-parcel.html',
                context=email_context
            )
        else:
            logger.warning(f"Parcel {parcel.external_id} created, but no email sent due to missing recipient email address.")


        response_serializer = ParcelSerializer(parcel)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    except ValueError as ve:
        return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error creating parcel: {e}", exc_info=True)
        return Response({"error": "An unexpected error occurred while creating the parcel."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_parcels_view(request):
    """
    Lists parcels. By default, lists non-picked-up parcels.
    Query param `status=all` to list all parcels.
    Query param `status=pickedup` to list only picked-up parcels.
    """
    list_parcels_view.required_groups = ['ADMIN', 'Verwaltung']
    # list_parcels_view.required_employee_types = ['DEPARTMENT']

    parcel_status_filter = request.GET.get('status', 'pending').lower()

    queryset = Parcel.objects.select_related('tenant', 'subtenant', 'subtenant__room').all()

    if parcel_status_filter == 'pending':
        queryset = queryset.filter(picked_up__isnull=True)
    elif parcel_status_filter == 'pickedup':
        queryset = queryset.filter(picked_up__isnull=False)
    elif parcel_status_filter != 'all':
        return Response({"error": "Invalid status filter. Use 'pending', 'pickedup', or 'all'."}, status=status.HTTP_400_BAD_REQUEST)

    # Order by arrival, newest first
    parcels = queryset.order_by('-arrived')
    serializer = ParcelSerializer(parcels, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def pickup_parcel_view(request, external_id):
    """
    Marks a parcel as picked up.
    """
    pickup_parcel_view.required_groups = ['ADMIN', 'Verwaltung']
    # pickup_parcel_view.required_employee_types = ['DEPARTMENT'] 

    try:
        parcel = Parcel.objects.get(external_id=external_id)
    except Parcel.DoesNotExist:
        return Response({"error": "Parcel not found."}, status=status.HTTP_404_NOT_FOUND)

    if parcel.picked_up:
        return Response({"message": "Parcel already marked as picked up.", "data": ParcelSerializer(parcel).data}, status=status.HTTP_200_OK)

    parcel.picked_up = timezone.now()
    parcel.save()
    logger.info(f"Parcel {parcel.external_id} marked as picked up by user {request.user.username}.")

    serializer = ParcelSerializer(parcel)
    return Response(serializer.data, status=status.HTTP_200_OK)