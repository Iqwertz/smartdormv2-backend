from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone

from ..permissions import GroupAndEmployeeTypePermission
from ..models import Tenant
from ..serializers import TenantForSelectSerializer

import logging

logger = logging.getLogger(__name__)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def tenants_for_select_view(request):
    """
    API endpoint to retrieve a list of current tenants with minimal data 
    (id, name, surname, username, current_room) for use in select dropdowns.
    """
    tenants_for_select_view.required_employee_types = ['DEPARTMENT']
    
    today = timezone.now().date()
    
    try:
        current_tenants = Tenant.objects.filter(
            move_in__lte=today,
            move_out__gte=today
        ).order_by('surname', 'name')
        
        serializer = TenantForSelectSerializer(current_tenants, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error retrieving tenants for select: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving tenant list for selection."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

