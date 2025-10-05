import json
import requests
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.middleware.csrf import get_token
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.http import HttpResponseServerError, HttpResponse
import logging
import uuid
from smartdorm.serializers import TenantSerializer, EngagementSerializer, HsvTenantSerializer
from ..models import Engagement
from ..utils import email_utils, pdf_utils
from .. import config as app_config
from django.db.models import Prefetch, Max
from django.utils import timezone  
from collections import defaultdict
from django.db.models import F
from django.db import transaction
from django.core.cache import cache
from rest_framework.parsers import MultiPartParser, FormParser


from ..permissions import GroupAndEmployeeTypePermission
from ..models import Tenant, Engagement, GlobalAppSettings, Departure, DepositBank, Claim, EngagementApplication
from ..serializers import TenantSerializer, GlobalAppSettingsSerializer, DepartureSerializer, EngagementApplicationCreateSerializer, EngagementApplicationListSerializer, MyEngagementApplicationSerializer
from ..utils.helper import create_and_notify_departure_signatures, get_next_semester

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
        

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def hsv_engagement_list_view(request):
    today = timezone.now().date()
    settings = GlobalAppSettings.load()

    semester_filter = request.GET.get('semester', None)
    if not semester_filter:
        semester_filter = settings.current_semester

    try:
        active_tenant_ids = Tenant.objects.filter(
            move_in__lte=today,
            move_out__gte=today
        ).values_list('id', flat=True)

        engagements_query = Engagement.objects.filter(
            tenant_id__in=active_tenant_ids,
            semester=semester_filter
        ).select_related('tenant', 'department').order_by(
            'department__name', 'tenant__surname', 'tenant__name' 
        )

        grouped_engagements = defaultdict(list)
        department_details = {}

        for eng in engagements_query:
            dept_id = eng.department.id
            if dept_id not in department_details:
                 department_details[dept_id] = {
                     'name': eng.department.name,
                     'full_name': eng.department.full_name
                 }
            grouped_engagements[dept_id].append(eng.tenant)

        output_data = []
        for dept_id, tenants in grouped_engagements.items():
            dept_info = department_details[dept_id]
            output_data.append({
                'department_id': dept_id,
                'department_name': dept_info['name'],
                'department_full_name': dept_info['full_name'],
                'semester': semester_filter, 
                'tenants': HsvTenantSerializer(tenants, many=True).data
            })

        output_data.sort(key=lambda x: x['department_name'])

        return Response(output_data, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"Error retrieving HSV engagement data: {e}")
        import traceback
        traceback.print_exc()
        return Response(
            {"error": "An error occurred while retrieving HSV data."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_global_settings_view(request):
    """
    API endpoint to retrieve all global application settings.
    """
    try:
        settings = GlobalAppSettings.load()
        serializer = GlobalAppSettingsSerializer(settings)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error retrieving global settings: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while retrieving global settings."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        

@api_view(['GET'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@authentication_classes([SessionAuthentication])
def my_departure_view(request):
    my_departure_view.required_employee_types = ['TENANT']
    
    try:
        tenant = Tenant.objects.get(username=request.user.username)
        departure = Departure.objects.get(tenant=tenant, status=Departure.Status.CREATED)
        serializer = DepartureSerializer(departure)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except (Tenant.DoesNotExist, Departure.DoesNotExist):
        return Response({"detail": "No open departure request found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error fetching departure for user {request.user.username}: {e}", exc_info=True)
        return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@authentication_classes([SessionAuthentication])
@transaction.atomic
def decide_departure_view(request):
    decide_departure_view.required_employee_types = ['TENANT']

    decision = request.data.get('decision', '').upper()
    if decision not in ['CONFIRM', 'POSTPONE']:
        return Response({"error": "Invalid decision. Must be 'CONFIRM' or 'POSTPONE'."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        tenant = Tenant.objects.get(username=request.user.username)
        departure = Departure.objects.get(tenant=tenant, status=Departure.Status.CREATED)
    except (Tenant.DoesNotExist, Departure.DoesNotExist):
        return Response({"error": "No open departure request found to decide on."}, status=status.HTTP_404_NOT_FOUND)

    if decision == 'POSTPONE':
        departure.status = Departure.Status.POSTPONED
        departure.save()
        # Create a new claim for extension
        max_id_result = Claim.objects.aggregate(max_id=Max('id'))
        new_id = (max_id_result['max_id'] or 0) + 1
        Claim.objects.create(
            id=new_id, external_id=uuid.uuid4().hex, tenant=tenant,
            status=Claim.Status.CREATED, type=Claim.Type.EXTENSION,
            created_on=timezone.now().date()
        )
        
        pdf_data = pdf_utils.prepare_extension_application_pdf_data(tenant)
        
        # Send email notification to the department
        email_utils.send_email_message(
            recipient_list=[app_config.DEPARTMENT_EMAIL],
            subject=f"{tenant.name} {tenant.surname} möchte verlängern",
            html_template_name='email/management-departure-postponement.html',
            context={
                'name': f"{tenant.name} {tenant.surname}",
                'room': tenant.current_room if tenant.current_room else 'Unbekannt',
            }
        )
        
        #Send email to tenant
        email_utils.send_email_message(
            recipient_list=[tenant.email],
            subject=f"Wohnzeitverlängerungsbewerbung",
            html_template_name='email/tenant-departure-postponement.html',
            context={
                'name': f"{tenant.name} {tenant.surname}",
                'room': tenant.current_room if tenant.current_room else 'Unbekannt',
            },
            dynamic_pdf_template_path='pdf/Wohnzeitverlaengerung-Bewerbungsformular.pdf',
            dynamic_pdf_data=pdf_data,
            dynamic_pdf_filename=f"Antrag_Wohnzeitverlaengerung_{tenant.surname}.pdf"
        )

        return Response({"message": "Departure successfully postponed."}, status=status.HTTP_200_OK)

    elif decision == 'CONFIRM':
        iban = request.data.get('iban')
        name = request.data.get('name')
        if not iban or not name:
            return Response({"error": "IBAN and account holder name are required to confirm departure."}, status=status.HTTP_400_BAD_REQUEST)

        # Create or update bank details
        DepositBank.objects.update_or_create(
            tenant=tenant,
            defaults={'name': name, 'iban': iban}
        )

        departure.status = Departure.Status.CONFIRMED
        departure.save()

        # Create open signatures and notify departments
        create_and_notify_departure_signatures(departure)

        # Send email notification to the department
        email_utils.send_email_message(
            recipient_list=[app_config.DEPARTMENT_EMAIL],
            subject=f"{tenant.name} {tenant.surname} möchte ausziehen",
            html_template_name='email/management-departure-confirmation.html',
            context={
                'name': f"{tenant.name} {tenant.surname}",
                'room': tenant.current_room if tenant.current_room else 'Unbekannt',
                'departureDate': tenant.move_out,
            }
        )
        
        #Send email to tenant
        email_utils.send_email_message(
            recipient_list=[tenant.email],
            subject="Dein Auszug aus dem Schollheim",
            html_template_name='email/tenant-departure-confirmation.html',
            context={
                'greeting': {tenant.name},
                'departureDate': tenant.move_out,
            }
        )

        return Response({"message": "Departure successfully confirmed."}, status=status.HTTP_200_OK)

    return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@authentication_classes([SessionAuthentication])
@parser_classes([MultiPartParser, FormParser])
def create_engagement_application_view(request):
    create_engagement_application_view.required_employee_types = ['TENANT']

    settings = GlobalAppSettings.load()
    if not settings.applications_open:
        return Response({"error": "Applications are currently closed."}, status=status.HTTP_403_FORBIDDEN)

    try:
        tenant = Tenant.objects.get(username=request.user.username)
    except Tenant.DoesNotExist:
        return Response({"error": "Tenant profile not found."}, status=status.HTTP_404_NOT_FOUND)

    next_semester = get_next_semester(settings.current_semester)
    if not next_semester:
        return Response({"error": "Could not determine the application semester."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Check for existing application for the same department in the same semester
    department_id = request.data.get('department')
    if EngagementApplication.objects.filter(tenant=tenant, semester=next_semester, department_id=department_id).exists():
        return Response({"error": f"You have already applied for this department for the {next_semester} semester."}, status=status.HTTP_409_CONFLICT)
    
    data = request.data.copy()
    serializer = EngagementApplicationCreateSerializer(data=data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = serializer.validated_data

    max_id_result = EngagementApplication.objects.aggregate(max_id=Max('id'))
    new_id = (max_id_result['max_id'] or 0) + 1

    image_file = request.FILES.get('image')

    try:
        EngagementApplication.objects.create(
            id=new_id,
            external_id=uuid.uuid4().hex,
            tenant=tenant,
            semester=next_semester,
            department=validated_data['department'],
            motivation=validated_data['motivation'],
            image=image_file.read() if image_file else None,
            image_name=image_file.name if image_file else None,
        )
        return Response({"message": "Application submitted successfully."}, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.error(f"Error creating engagement application for {tenant.username}: {e}", exc_info=True)
        return Response({"error": "An internal error occurred while saving the application."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def list_engagement_applications_view(request):
    settings = GlobalAppSettings.load()
    if not settings.show_applications:
        return Response([], status=status.HTTP_200_OK)

    next_semester = get_next_semester(settings.current_semester)
    if not next_semester:
        return Response({"error": "Could not determine the application semester."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # --- THE FIX: Use .values() for maximum performance ---
    # We select only the data we need, directly into dictionaries.
    # This avoids creating expensive model instances.
    applications_data = EngagementApplication.objects.filter(
        semester=next_semester
    ).order_by('department_id', 'tenant_id').values(
        'id',
        'motivation',
        'image_name',  # Fetching the small image_name is fast
        'tenant__name',
        'tenant__surname',
        'department__id',
        'department__full_name'
    )

    # Manually construct the final JSON structure, which is very fast.
    results = []
    for app in applications_data:
        image_url = None
        # If there's an image_name, an image exists.
        if app['image_name']:
            image_url = request.build_absolute_uri(
                reverse('tenants:get-application-image', kwargs={'app_id': app['id']})
            )

        results.append({
            'id': app['id'],
            'motivation': app['motivation'],
            'tenant': {
                'name': app['tenant__name'],
                'surname': app['tenant__surname']
            },
            'department': {
                'id': app['department__id'],
                'full_name': app['department__full_name']
                # The frontend doesn't need department 'name', only 'full_name'
            },
            'image_url': image_url
        })

    return Response(results)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def get_application_image_view(request, app_id):
    """
    Serves the image for a specific engagement application.
    Permissions are checked based on the main list view's logic.
    """
    settings = GlobalAppSettings.load()
    if not settings.show_applications:
        # If applications aren't visible, tenants shouldn't access images either
        raise Http404

    cache_key = f"appimg:{app_id}"
    cached_bytes = cache.get(cache_key)
    if cached_bytes:
        resp = HttpResponse(cached_bytes, content_type='image/jpeg')
        resp['Cache-Control'] = 'public, max-age=5184000, immutable'
        return resp

    application = get_object_or_404(EngagementApplication, id=app_id)
    if not application.image:
        raise Http404

    img_bytes = application.image.tobytes() if hasattr(application.image, 'tobytes') else bytes(application.image)
    try:
        cache.set(cache_key, img_bytes, timeout=5184000)
    except Exception:
        pass
    resp = HttpResponse(img_bytes, content_type='image/jpeg')
    resp['Cache-Control'] = 'public, max-age=5184000, immutable'
    return resp
    


@api_view(['GET'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@authentication_classes([SessionAuthentication])
def my_engagement_applications_view(request):
    my_engagement_applications_view.required_employee_types = ['TENANT']

    try:
        tenant = Tenant.objects.get(username=request.user.username)
        applications = EngagementApplication.objects.filter(tenant=tenant).order_by('-semester', 'department__name')
        serializer = MyEngagementApplicationSerializer(applications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Tenant.DoesNotExist:
        return Response({"error": "Tenant profile not found."}, status=status.HTTP_404_NOT_FOUND)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@authentication_classes([SessionAuthentication])
def delete_engagement_application_view(request, app_id):
    delete_engagement_application_view.required_employee_types = ['TENANT']

    settings = GlobalAppSettings.load()
    if not settings.applications_open:
        return Response({"error": "Applications are closed and cannot be modified."}, status=status.HTTP_403_FORBIDDEN)

    try:
        tenant = Tenant.objects.get(username=request.user.username)
        application = EngagementApplication.objects.get(id=app_id, tenant=tenant)
        
        # To prevent deleting old applications, only allow deletion for the upcoming semester.
        next_semester = get_next_semester(settings.current_semester)
        if application.semester != next_semester:
            return Response({"error": "You can only delete applications for the upcoming semester."}, status=status.HTTP_403_FORBIDDEN)

        application.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except Tenant.DoesNotExist:
        return Response({"error": "Tenant profile not found."}, status=status.HTTP_404_NOT_FOUND)
    except EngagementApplication.DoesNotExist:
        return Response({"error": "Application not found or you do not have permission to delete it."}, status=status.HTTP_404_NOT_FOUND)