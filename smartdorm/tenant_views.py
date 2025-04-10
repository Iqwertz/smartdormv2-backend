import json
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.middleware.csrf import get_token
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status

from .permissions import GroupAndEmployeeTypePermission
from .models import Tenant
from .serializers import TenantSerializer

@api_view(['GET'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@authentication_classes([SessionAuthentication])
def profile_data_view(request):
    """
    Responds with the Tenant object associated with the currently logged-in user.
    """
    profile_data_view.required_employee_types = ['TENANT']

    logged_in_username = request.user.username

    try:
        tenant = Tenant.objects.get(username=logged_in_username)
    except Tenant.DoesNotExist:
        return Response(
            {"error": "Tenant profile data not found for the logged-in user."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Tenant.MultipleObjectsReturned:
        # Dont know if this ist possible/how we handle users with the same username. But added it now for safety
        return Response(
             {"error": "Multiple tenant profiles found for the logged-in user. Please contact admin."},
             status=status.HTTP_500_INTERNAL_SERVER_ERROR
         )
    serializer = TenantSerializer(tenant)
    return Response(serializer.data, status=status.HTTP_200_OK)