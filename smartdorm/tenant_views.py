import json
import requests
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.middleware.csrf import get_token
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.http import HttpResponseServerError, HttpResponse
import logging
from smartdorm.serializers import TenantSerializer, EngagementSerializer

from .permissions import GroupAndEmployeeTypePermission
from .models import Tenant, Engagement
from .serializers import TenantSerializer

logger = logging.getLogger(__name__)

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


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def calendar_proxy_view(request):
    """
    Fetches the ICS calendar file from the configured Nextcloud URL
    and returns its content along with the source URL in a JSON object.
    Acts as a proxy to bypass CORS issues.
    """
    ics_url = settings.NEXTCLOUD_ICS_URL

    if not ics_url or ics_url == "YOUR_DEFAULT_NEXTCLOUD_ICS_LINK_HERE":
        logger.error("NEXTCLOUD_ICS_URL is not configured in settings.")
        # Return JSON error response
        return JsonResponse({"error": "Calendar service is not configured."}, status=500)

    try:
        response = requests.get(ics_url, timeout=10)
        response.raise_for_status()

        # Decode content to string, assuming UTF-8 which is common for ICS
        try:
            ics_data = response.content.decode('utf-8')
        except UnicodeDecodeError:
            # Fallback or log error if decoding fails
            logger.warning(f"Could not decode ICS from {ics_url} as UTF-8, trying fallback.")
            ics_data = response.text # requests might guess encoding

        # Prepare JSON response
        data = {
            "icsData": ics_data,
            "icsUrl": ics_url,
            "calendarUrl": settings.NEXTCLOUD_CALENDAR_URL,
        }
        # Return JSON
        return JsonResponse(data)

    except requests.exceptions.Timeout:
        logger.error(f"Timeout while fetching ICS from {ics_url}")
        return JsonResponse({"error": "Could not reach calendar server (timeout)."}, status=504) # Gateway Timeout
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching ICS from {ics_url}: {e}")
        status_code = response.status_code if 'response' in locals() and response else 502 # Bad Gateway
        return JsonResponse({"error": "Failed to fetch calendar data from source."}, status=status_code)
    except Exception as e:
        logger.exception(f"Unexpected error in calendar proxy view: {e}")
        return JsonResponse({"error": "An unexpected server error occurred."}, status=500)
    
    
@api_view(['GET'])
@permission_classes([IsAuthenticated]) # User must be logged in
@authentication_classes([SessionAuthentication])
def my_engagements_view(request):
    """
    Responds with a list of Engagement objects associated with the
    currently logged-in user, if they exist as a Tenant.
    """
    logged_in_username = request.user.username

    try:
        # Find the Tenant profile linked to the logged-in Django user
        tenant = Tenant.objects.get(username=logged_in_username)
        # Fetch engagements for this tenant
        engagements = Engagement.objects.filter(tenant=tenant).select_related('department').order_by('-semester') # Fetch department too
        serializer = EngagementSerializer(engagements, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Tenant.DoesNotExist:
        # If the logged-in user doesn't have a Tenant profile, return empty list
        return Response([], status=status.HTTP_200_OK) # Or 404 if you prefer
    except Tenant.MultipleObjectsReturned:
        # This shouldn't happen with unique usernames, but handle defensively
        return Response(
            {"error": "Multiple tenant profiles found for the logged-in user. Please contact admin."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
         # Catch other potential errors
        return Response(
            {"error": f"An unexpected error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )