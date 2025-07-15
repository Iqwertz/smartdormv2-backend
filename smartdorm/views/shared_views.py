from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone

from ..permissions import GroupAndEmployeeTypePermission
from ..models import Tenant, Subtenant, Room

import logging

logger = logging.getLogger(__name__)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def tenants_for_select_view(request):
    """
     API endpoint to retrieve a list of current tenants with minimal data 
     (id, name, surname, username, current_room) for use in select dropdowns.
    Accepts an 'include' query parameter:
    - 'tenants' (default): Only tenants
    - 'subtenants': Only subtenants
    - 'all': Both tenants and subtenants
     """
    
    today = timezone.now().date()
    
    include_filter = request.GET.get('include', 'tenants').lower()    
    recipients_list = []
    
    try:
        # Fetch Tenants
        if include_filter in ['tenants', 'all']:
            current_tenants = Tenant.objects.filter(
                move_in__lte=today,
                move_out__gte=today
            ).order_by('surname', 'name')
            for tenant in current_tenants:
                recipients_list.append({
                    'id': tenant.id,
                    'name': tenant.name,
                    'surname': tenant.surname,
                    'username': tenant.username,
                    'current_room': tenant.current_room,
                    'label': f"{tenant.name} {tenant.surname} ({tenant.username or 'N/A'}) - Zimmer: {tenant.current_room or 'N/A'} (Mieter)",
                    'type': 'tenant'
                })

        if include_filter in ['subtenants', 'all']:
            current_subtenants = Subtenant.objects.filter(
                move_in__lte=today,
                move_out__gte=today
            ).select_related('room').order_by('surname', 'name')
            for subtenant in current_subtenants:
                room_name = subtenant.room.name if subtenant.room else 'N/A'
                recipients_list.append({
                    'id': f's_{subtenant.id}',
                    'name': subtenant.name,
                    'surname': subtenant.surname,
                    'username': None, # Subtenants don't have usernames in the Tenant model sense
                    'current_room': room_name, # Room they are sub-renting
                    'label': f"{subtenant.name} {subtenant.surname} - Zimmer: {room_name} (Untermieter)",
                    'type': 'subtenant'
                })
        
        # Sort the combined list by label for a consistent order in the dropdown
        recipients_list.sort(key=lambda x: x['label'])
        
        return Response(recipients_list, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error retrieving recipients for select (filter: {include_filter}): {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving recipient list for selection."},
             status=status.HTTP_500_INTERNAL_SERVER_ERROR
         )

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def rooms_for_select_view(request):
    """
    API endpoint to retrieve a list of all rooms for select dropdowns.
    """
    try:
        rooms = Room.objects.all().order_by('name')
        room_list = [
            {'id': room.id, 'label': room.name} for room in rooms
        ]
        return Response(room_list, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error retrieving rooms for select: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving room list."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )