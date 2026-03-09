#In this file we have all views that are in some way restricted to a engagement role
from django.http import HttpResponse
from django.utils import timezone
from django.urls import reverse
from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Max, Sum, Count, Prefetch
import uuid
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.core.cache import cache
import time
import threading

from ..utils.helper import checkValidSemesterFormat, get_next_semester
from ..utils.email_utils import send_email_message
from ..permissions import GroupAndEmployeeTypePermission
from ..models import EngagementApplication, GlobalAppSettings, Engagement, Tenant, Department
from ..serializers import (
    DepartmentSerializer, GlobalAppSettingsSerializer, EngagementApplicationListSerializer,
    HeimratEngagementApplicationCreateSerializer, AdminEngagementListSerializer,
    EngagementCreateByHeimratSerializer, EngagementUpdateSerializer, NewDepartmentSerializer, TenantOverviewSerializer
)
from ..utils import ldap_utils
from rest_framework.response import Response
from rest_framework import status

from io import BytesIO
from PIL import Image as PILImage

import csv

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    PageBreak
)

import re
from collections import defaultdict

import logging
logger = logging.getLogger(__name__)

class PDFGenerator:
    """Class to handle PDF generation for engagement applications,
       grouped by department with a table of contents."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.toc_style = ParagraphStyle(
            'TOCEntry',
            parent=self.styles['Normal'],
            leftIndent=20, # Indent TOC entries
            spaceBefore=2,
            spaceAfter=2
        )
        self.section_title_style = ParagraphStyle(
            'SectionTitle',
            parent=self.styles['Heading1'], # Use Heading1 for main sections
            spaceAfter=16,
            keepWithNext=1 # Try to keep title with the first paragraph
        )
        self.application_heading_style = ParagraphStyle(
            'AppHeading',
            parent=self.styles['Heading2'], # Use Heading2 for individual applications
            spaceBefore=12,
            spaceAfter=6
        )
        self.normal_style = self.styles['Normal']

        self.pagesize = A4
        self.available_width = self.pagesize[0] - 2 * inch
        self.max_img_width = 2.5 * inch
        self.max_img_height = 3 * inch

    def _sanitize_anchor_name(self, name):
        """Creates a safe anchor name from a string."""
        # Remove non-alphanumeric characters (except hyphen/underscore)
        name = re.sub(r'[^\w-]', '', name.lower().replace(' ', '_'))
        # Ensure it doesn't start with a number (HTML4 compatibility)
        if name and name[0].isdigit():
            name = '_' + name
        return name or "default_anchor" # Fallback

    def resize_image(self, img_data, max_w, max_h):
        try:
            # Ensure img_data is seekable (BytesIO is good)
            if not hasattr(img_data, 'seek'):
                 img_data = BytesIO(img_data)
            img_data.seek(0) # Reset stream position

            pil_img = PILImage.open(img_data)
            pil_img.verify() # Check if image is valid
            # Re-open after verify
            img_data.seek(0)
            pil_img = PILImage.open(img_data)

            img_w, img_h = pil_img.size
            if img_w <= 0 or img_h <= 0:
                 raise ValueError("Invalid image dimensions")
            aspect = img_w / float(img_h)

            # Simplified logic: scale to fit within bounds while maintaining aspect ratio
            scale_w = max_w / img_w
            scale_h = max_h / img_h
            scale = min(scale_w, scale_h)

            final_w = img_w * scale
            final_h = img_h * scale

            # Need to pass the BytesIO object back to ReportLab Image
            img_data.seek(0)
            return Image(img_data, width=final_w, height=final_h)

        except Exception as e:
            # Log the error for debugging
            print(f"Error processing image: {e}")
            return Paragraph(f"<para textColor='red'>[Bild konnte nicht geladen werden: {e}]</para>", self.normal_style)

    def create_application_element(self, application):
        """Creates ReportLab flowables for a single application,
           placing text first, then the image below if present."""
        elements = []

        # Application Heading (Name)
        elements.append(Paragraph(
            f"{application.tenant.name} {application.tenant.surname}",
            self.application_heading_style
        ))
        elements.append(Spacer(1, 0.1 * inch)) # Small spacer after heading

        # Motivation Text (This can now split across pages)
        # Use replace('<br/>') for explicit line breaks from the text field
        motivation_text = application.motivation.replace('\n', '<br/>') if application.motivation else ""
        elements.append(Paragraph(motivation_text, self.normal_style))
        elements.append(Spacer(1, 0.2 * inch)) # Spacer after motivation text

        # Image (If it exists)
        if application.image:
            img_content = self.resize_image(
                application.image,
                self.max_img_width,
                self.max_img_height
            )
            # Append the image (potentially wrapped for centering or alignment)
            elements.append(img_content)
            elements.append(Spacer(1, 0.2 * inch)) # Spacer after image

        # Add a larger spacer after the entire application element is done
        elements.append(Spacer(1, 0.4 * inch))

        # Optional: Wrap in KeepTogether if you want to try and keep *short*
        # applications together, but it won't help with very long text.
        # return [KeepTogether(elements)]
        return elements

    def generate_pdf(self, applications, title="Bewerbungen - Unsortiert"):
        """Generates the PDF with TOC and grouped applications."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=self.pagesize)
        story = [] # Use 'story' as the conventional name for ReportLab elements

        # --- 1. Group applications by department ---
        grouped_applications = defaultdict(list)
        for app in applications:
            # Handle potential null departments gracefully
            dept_name = app.department.name if app.department else "Ohne Referatszuordnung"
            grouped_applications[dept_name].append(app)

        # Sort department names for consistent TOC and section order
        sorted_dept_names = sorted(grouped_applications.keys())

        # --- 2. Build Table of Contents Elements ---
        toc_elements = [
            Paragraph("Inhaltsverzeichnis", self.section_title_style),
            Spacer(1, 0.05 * inch),
            Paragraph("Gerne draufklicken", self.normal_style),
            Spacer(1, 0.2 * inch)
        ]
        department_anchors = {} # Store anchor names for later use
        for dept_name in sorted_dept_names:
            anchor_name = self._sanitize_anchor_name(dept_name)
            department_anchors[dept_name] = anchor_name
            # Create clickable link in TOC
            toc_link = f'<a href="#{anchor_name}">{dept_name}</a> ({len(grouped_applications[dept_name])} Bewerbungen)'
            toc_elements.append(Paragraph(toc_link, self.toc_style))

        # --- 3. Build Main Document Elements ---
        main_elements = [Paragraph(title, self.section_title_style)] # Main PDF Title
        main_elements.extend(toc_elements)
        main_elements.append(PageBreak()) # Page break after TOC

        # --- 4. Add Department Sections ---
        for dept_name in sorted_dept_names:
            anchor_name = department_anchors[dept_name]

            # Add the anchor target (invisible)
            story.append(Paragraph(f'<a name="{anchor_name}"/>', self.normal_style))
            # Add the department section title
            story.append(Paragraph(dept_name, self.section_title_style))
            story.append(Spacer(1, 0.2 * inch))

            # Add applications for this department
            apps_in_dept = grouped_applications[dept_name]
            for i, application in enumerate(apps_in_dept):
                story.extend(self.create_application_element(application))
                # Optional: Add a subtle separator between applications if needed
                # if i < len(apps_in_dept) - 1:
                #    story.append(HRFlowable(width="80%", thickness=0.5, color=colors.grey, spaceBefore=5, spaceAfter=5))

            # Add page break after each department section (except the last one)
            if dept_name != sorted_dept_names[-1]:
                story.append(PageBreak())

        # --- 5. Build the PDF ---
        # Combine title, TOC, and main content
        full_story = main_elements + story
        doc.build(full_story)

        pdf = buffer.getvalue()
        buffer.close()
        return pdf

def _get_or_generate_cached_pdf(semester):
    """
    Handles PDF generation with caching and locking to prevent race conditions.
    Returns the PDF bytes, b'NOT_FOUND' if no applications, or None on timeout.
    """
    cache_key = f"applications_pdf_{semester}"
    lock_key = f"lock_applications_pdf_{semester}"

    pdf_data = cache.get(cache_key)
    if pdf_data:
        return pdf_data

    if cache.add(lock_key, 'generating', timeout=120):  # Lock for 2 minutes
        try:
            logger.info(f"Cache miss for {cache_key}. Generating PDF.")
            applications = EngagementApplication.objects.select_related(
                'department', 'tenant'
            ).filter(semester=semester).order_by('department__name', 'tenant__surname', 'tenant__name')

            if not applications.exists():
                cache.set(cache_key, b'NOT_FOUND', timeout=3600)
                return b'NOT_FOUND'

            pdf_generator = PDFGenerator()
            pdf_title = f"Referatsbewerbungen - {semester}"
            pdf_data = pdf_generator.generate_pdf(applications, title=pdf_title)
            cache.set(cache_key, pdf_data, timeout=None)
            logger.info(f"Successfully generated and cached PDF for {semester}.")
            return pdf_data
        finally:
            cache.delete(lock_key)
    else:
        # Another process is generating, wait and retry
        for _ in range(15):  # Wait up to 15 seconds
            time.sleep(1)
            pdf_data = cache.get(cache_key)
            if pdf_data:
                return pdf_data
        logger.warning(f"Timeout waiting for PDF generation for semester {semester}.")
        return None

def trigger_pdf_regeneration(semester):
    """
    Invalidates the cache and triggers an asynchronous regeneration of the PDF.
    """
    cache_key = f"applications_pdf_{semester}"
    logger.info(f"Invalidating cache and triggering async PDF regeneration for semester: {semester}")
    cache.delete(cache_key)

    # Run the PDF generation in a background thread
    thread = threading.Thread(target=_get_or_generate_cached_pdf, args=(semester,))
    thread.daemon = True  # Allows the main program to exit even if threads are running
    thread.start()

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_applications_pdf(request):
    """
    Serves a cached PDF of engagement applications for a given semester.
    Accessible to all tenants, but respects the 'show_applications' global setting.
    """
    get_applications_pdf.required_employee_types = ['TENANT']
    settings = GlobalAppSettings.load()

    semester = request.GET.get('semester')
    
    if not settings.show_applications and semester == get_next_semester(settings.current_semester):
        return Response({"error": "Applications are not currently visible to tenants."}, status=status.HTTP_403_FORBIDDEN)
    
    if not semester:
        semester = get_next_semester(settings.current_semester)
    
    if not checkValidSemesterFormat(semester):
        return Response({"error": "Invalid semester format. Use SSYY or WSYY/YY."}, status=status.HTTP_400_BAD_REQUEST)

    pdf_data = _get_or_generate_cached_pdf(semester)

    if pdf_data is None:
        return Response(
            {"error": "PDF is currently being generated. Please try again in a moment."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    if pdf_data == b'NOT_FOUND':
        return HttpResponse(f"Keine Bewerbungen für das Semester {semester} gefunden.", status=404)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="referatsbewerbungen_{semester.replace("/", "-")}.pdf"'
    response.write(pdf_data)

    return response

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def set_current_semester_view(request):
    """
    API endpoint to set the current_semester.
    Requires user to be in 'Heimrat' or 'Netzwerkreferat' group.
    Expects JSON: {"current_semester": "SS2025"}
    Uses POST method.
    """
    set_current_semester_view.required_groups = ['Heimrat', 'Netzwerkreferat']
    # set_current_semester_view.required_employee_types = []

    new_semester = request.data.get('current_semester')
    
    if not new_semester or not isinstance(new_semester, str) or not checkValidSemesterFormat(new_semester):
        return Response(
            {"error": "Field 'current_semester' is required and must be a string in the format SSYY or WSYY/YY."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        settings = GlobalAppSettings.load()
        settings.current_semester = new_semester
        settings.save()
        serializer = GlobalAppSettingsSerializer(settings)
        logger.info(f"User '{request.user.username}' updated current_semester to '{new_semester}'.")
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error setting current semester: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while updating the current semester."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST']) 
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def set_applications_open_view(request):
    """
    API endpoint to set the applications_open status.
    Requires user to be in 'Heimrat' or 'Netzwerkreferat' group.
    Expects JSON: {"applications_open": true}
    Uses POST method.
    """
    set_applications_open_view.required_groups = ['Heimrat', 'Netzwerkreferat']
    # set_applications_open_view.required_employee_types = []

    applications_open_status = request.data.get('applications_open')
    if applications_open_status is None or not isinstance(applications_open_status, bool):
        return Response(
            {"error": "Field 'applications_open' is required and must be a boolean (true/false)."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        settings = GlobalAppSettings.load()
        settings.applications_open = applications_open_status
        settings.save()
        serializer = GlobalAppSettingsSerializer(settings)
        logger.info(f"User '{request.user.username}' updated applications_open to '{applications_open_status}'.")
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error setting applications open status: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while updating the applications open status."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        
@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def set_show_applications_view(request):
    """
    API endpoint to set the show_applications status.
    Requires user to be in 'Heimrat' or 'Netzwerkreferat' group.
    Expects JSON: {"show_applications": true}
    """
    set_show_applications_view.required_groups = ['Heimrat', 'Netzwerkreferat']

    show_applications_status = request.data.get('show_applications')
    if show_applications_status is None or not isinstance(show_applications_status, bool):
        return Response(
            {"error": "Field 'show_applications' is required and must be a boolean (true/false)."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        settings = GlobalAppSettings.load()
        settings.show_applications = show_applications_status
        settings.save()
        serializer = GlobalAppSettingsSerializer(settings)
        logger.info(f"User '{request.user.username}' updated show_applications to '{show_applications_status}'.")
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error setting show_applications status: {e}", exc_info=True)
        return Response(
            {"error": "An error occurred while updating the show_applications status."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def heimrat_list_applications_view(request):
    heimrat_list_applications_view.required_groups = ['Heimrat', 'ADMIN']

    settings = GlobalAppSettings.load()
    next_semester = get_next_semester(settings.current_semester)
    if not next_semester:
        return Response({"error": "Could not determine the application semester."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # --- THE FIX: Use .values() for maximum performance ---
    applications_data = EngagementApplication.objects.filter(
        semester=next_semester
    ).order_by('department_id', 'tenant_id').values(
        'id',
        'motivation',
        'image_name',
        'tenant__name',
        'tenant__surname',
        'department__id',
        'department__full_name'
    )

    results = []
    for app in applications_data:
        image_url = None
        if app['image_name']:
            image_url = request.build_absolute_uri(
                reverse('engagements:heimrat-get-application-image', kwargs={'app_id': app['id']})
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
            },
            'image_url': image_url
        })
    return Response(results)

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def heimrat_get_application_image_view(request, app_id):
    """ Serves an application image specifically for Heimrat, bypassing visibility settings. """
    heimrat_get_application_image_view.required_groups = ['Heimrat', 'ADMIN']
    
    application = get_object_or_404(EngagementApplication, id=app_id)
    if not application.image:
        raise Http404

    return HttpResponse(application.image, content_type='image/jpeg')

@api_view(['DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def heimrat_delete_application_view(request, app_id):
    """
    API endpoint for Heimrat to delete any engagement application.
    """
    heimrat_delete_application_view.required_groups = ['Heimrat', 'ADMIN']

    try:
        application = EngagementApplication.objects.get(id=app_id)
        application_semester = application.semester
        application.delete()
        trigger_pdf_regeneration(application_semester)
        return Response(status=status.HTTP_204_NO_CONTENT)
    except EngagementApplication.DoesNotExist:
        return Response({"error": "Application not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@parser_classes([MultiPartParser, FormParser])
def heimrat_create_application_view(request):
    """
    API endpoint for Heimrat to create an application on behalf of a tenant,
    bypassing the 'applications_open' check.
    """
    heimrat_create_application_view.required_groups = ['Heimrat', 'ADMIN']
    
    settings = GlobalAppSettings.load()
    next_semester = get_next_semester(settings.current_semester)
    if not next_semester:
        return Response({"error": "Could not determine the application semester."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    data = request.data.copy()
    tenant_id = data.get('tenant')
    department_id = data.get('department')

    if EngagementApplication.objects.filter(tenant_id=tenant_id, semester=next_semester, department_id=department_id).exists():
        return Response({"error": f"This tenant has already applied for this department for the {next_semester} semester."}, status=status.HTTP_409_CONFLICT)

    serializer = HeimratEngagementApplicationCreateSerializer(data=data)
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
            tenant=validated_data['tenant'],
            semester=next_semester,
            department=validated_data['department'],
            motivation=validated_data['motivation'],
            image=image_file.read() if image_file else None,
            image_name=image_file.name if image_file else None,
        )
        trigger_pdf_regeneration(next_semester)
        return Response({"message": "Application created successfully on behalf of the tenant."}, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.error(f"Heimrat error creating engagement application: {e}", exc_info=True)
        return Response({"error": "An internal error occurred while saving the application."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

HEIMRAT_INFO_GROUPS = ['Heimrat', 'Inforeferat', 'ADMIN']

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_engagements_admin_view(request):
    """
    Lists engagements, filterable by compensation status.
    ?compensated=true or ?compensated=false
    """
    list_engagements_admin_view.required_groups = HEIMRAT_INFO_GROUPS

    compensated = request.query_params.get('compensated', '').lower()
    if compensated not in ['true', 'false']:
        return Response({"error": "Query parameter 'compensated' must be 'true' or 'false'."}, status=status.HTTP_400_BAD_REQUEST)

    queryset = Engagement.objects.filter(
        compensate=(compensated == 'true')
    ).select_related('tenant', 'department').order_by('-semester', 'tenant__surname')
    
    serializer = AdminEngagementListSerializer(queryset, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def create_engagement_admin_view(request):
    """ Creates a new engagement for a tenant. """
    create_engagement_admin_view.required_groups = HEIMRAT_INFO_GROUPS

    serializer = EngagementCreateByHeimratSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    department = Department.objects.get(id=data['department_id'])
    
    max_id_result = Engagement.objects.aggregate(max_id=Max('id'))
    new_id = (max_id_result['max_id'] or 0) + 1
    
    engagement = Engagement.objects.create(
        id=new_id,
        external_id=uuid.uuid4().hex,
        tenant_id=data['tenant_id'],
        department_id=data['department_id'],
        semester=data['semester'],
        note=data.get('note', ''),
        compensate=data.get('compensate', False),
        points=department.points
    )
    
    # Update tenant's total compensated points if this engagement is compensated
    if engagement.compensate:
        tenant = Tenant.objects.get(id=data['tenant_id'])
        total_points = Engagement.objects.filter(
            tenant=tenant, compensate=True
        ).aggregate(total=Sum('points'))['total'] or 0
        tenant.current_points = total_points
        tenant.save()
        

     
    
    # Send email to tenant about new engagement
    tenant = Tenant.objects.get(id=data['tenant_id'])
    
    send_email_message(
            recipient_list=[tenant.email],
            subject=f'Dein Amt {department.name}',
            html_template_name='email/tenant-engagement-creation.html',
            context={
                'greeting': tenant.name,
                'department': department.full_name,
                'semester': data['semester'],
            }
    )
    
    # Check if engagement is in current semester and update ldap roles
    settings = GlobalAppSettings.load()
    if data['semester'] == settings.current_semester:
        group_base_dn = "ou=groups2,dc=schollheim,dc=net"
        group_cn = _get_ldap_group_name_from_department(department.full_name, tenant)
        group_dn = f"cn={group_cn},{group_base_dn}"
        success = ldap_utils.add_user_to_group(tenant.username, group_dn)
        if success:
            logger.info(f"Added user '{tenant.username}' to LDAP group '{group_cn}' for engagement '{department.name}'.")
        else:
            logger.error(f"Failed to add user '{tenant.username}' to LDAP group '{group_cn}' for engagement '{department.name}'.")
        # Also add tenant to 'HSV' group
        hsv_group_dn = "cn=HSV,ou=groups2,dc=schollheim,dc=net"
        success_hsv = ldap_utils.add_user_to_group(tenant.username, hsv_group_dn)
        if success_hsv:
            logger.info(f"Added user '{tenant.username}' to LDAP group 'HSV' for engagement '{department.name}'.")
        else:
            logger.error(f"Failed to add user '{tenant.username}' to LDAP group 'HSV' for engagement '{department.name}'.")
            
    response_serializer = AdminEngagementListSerializer(engagement)
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)

@api_view(['PUT'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def update_engagement_view(request, engagement_id):
    """ Updates the entry for a specific engagement, points and note can be updated. """
    update_engagement_view.required_groups = HEIMRAT_INFO_GROUPS
    
    engagement = get_object_or_404(Engagement, id=engagement_id)
    serializer = EngagementUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    engagement.points = serializer.validated_data['points']
    engagement.note = serializer.validated_data.get('note', engagement.note)
    engagement.save()
    
    response_serializer = AdminEngagementListSerializer(engagement)
    return Response(response_serializer.data)

@api_view(['DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def delete_engagement_view(request, engagement_id):
    """ Deletes an engagement. """
    delete_engagement_view.required_groups = HEIMRAT_INFO_GROUPS
    
    engagement = get_object_or_404(Engagement, id=engagement_id)
    tenant = engagement.tenant
    engagement.delete()
    
    #Recalculate tenant's total compensated points
    total_points = Engagement.objects.filter(
        tenant=tenant, compensate=True
    ).aggregate(total=Sum('points'))['total'] or 0
    
    tenant.current_points = total_points
    tenant.save()
    
    #If engagement is in current semester, remove ldap role
    settings = GlobalAppSettings.load()
    if engagement.semester == settings.current_semester:
        group_base_dn = "ou=groups2,dc=schollheim,dc=net"
        group_cn = _get_ldap_group_name_from_department(engagement.department.full_name, tenant)
        group_dn = f"cn={group_cn},{group_base_dn}"
        success = ldap_utils.remove_user_from_group(tenant.username, group_dn)
        if success:
            logger.info(f"Removed user '{tenant.username}' from LDAP group '{group_cn}' for deleted engagement '{engagement.department.name}'.")
        else:
            logger.error(f"Failed to remove user '{tenant.username}' from LDAP group '{group_cn}' for deleted engagement '{engagement.department.name}'.")
        # Also remove from 'HSV' group
        hsv_group_dn = "cn=HSV,ou=groups2,dc=schollheim,dc=net"
        success_hsv = ldap_utils.remove_user_from_group(tenant.username, hsv_group_dn)
        
        if not success_hsv:
            logger.error(f"Failed to remove user '{tenant.username}' from LDAP group 'HSV' for deleted engagement '{engagement.department.name}'.")

    return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['PUT'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def toggle_engagement_compensate_view(request, engagement_id):
    """ Toggles the compensation status of a single engagement. """
    toggle_engagement_compensate_view.required_groups = HEIMRAT_INFO_GROUPS

    engagement = get_object_or_404(
        Engagement.objects.select_related('tenant', 'department'), 
        id=engagement_id
    )

    was_compensated_before = engagement.compensate
    new_compensate_status = not was_compensated_before

    engagement.compensate = new_compensate_status
    engagement.save()

    tenant = engagement.tenant
    
    # Recalculate tenant's total compensated points
    total_points = Engagement.objects.filter(
        tenant=tenant, compensate=True
    ).aggregate(total=Sum('points'))['total'] or 0
    
    tenant.current_points = total_points
    tenant.save()

    # Send email only when an engagement is marked as compensated
    if new_compensate_status:
        department = engagement.department
        send_email_message(
            recipient_list=[tenant.email],
            subject=f'Referatsentlastung {department.name}',
            html_template_name='email/tenant-engagement-compensation.html',
            context={
                'greeting': tenant.name,
                'department': department.full_name,
                'semester': engagement.semester,
                'points': engagement.points,
                'totalPoints': total_points
            }
        )
    else:
        # Optionally notify tenant about de-compensation
        send_email_message(
            recipient_list=[tenant.email],
            subject=f'Rücknahme der Referatsentlastung {engagement.department.name}',
            html_template_name='email/tenant-engagement-decompensation.html',
            context={
                'greeting': tenant.name,
                'department': engagement.department.full_name,
                'semester': engagement.semester,
                'points': engagement.points,
                'totalPoints': total_points
            }
        )

    return Response({"message": f"Engagement compensation status updated to {new_compensate_status}."})

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def compensate_all_engagements_view(request):
    """ Sets all uncompensated engagements to compensated and sends a mail to every tenant that had an engagement compensated. """
    compensate_all_engagements_view.required_groups = HEIMRAT_INFO_GROUPS
    
    # Find all engagements that are not yet compensated
    engagements_to_compensate = Engagement.objects.filter(compensate=False).select_related('tenant', 'department')
    
    engagements_list = list(engagements_to_compensate)
    updated_count = len(engagements_list)
    
    # Update the engagements in the database
    if updated_count > 0:
        engagement_ids = [eng.id for eng in engagements_list]
        Engagement.objects.filter(id__in=engagement_ids).update(compensate=True)

    # Notify tenants about their newly compensated engagements and update their total points
    for engagement in engagements_list:
        tenant = engagement.tenant
        department = engagement.department
        tenant_total_points = Engagement.objects.filter(tenant=tenant, compensate=True).aggregate(total=Sum('points'))['total'] or 0
        #Update the tenant total points in the tenant model
        tenant.current_points = tenant_total_points
        tenant.save()
        #Send the email to the tenant
        send_email_message(
            recipient_list=[tenant.email],
            subject=f'Referatsentlastung {department.name}',
            html_template_name='email/tenant-engagement-compensation.html',
            context={
                'greeting': tenant.name,
                'department': department.full_name,
                'semester': engagement.semester,
                'points': engagement.points,
                'totalPoints': tenant_total_points
            }
        )

    return Response({"message": f"{updated_count} engagement(s) successfully compensated."})



@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def export_engagement_tenants_csv(request):
    """
    API endpoint to export a CSV file of all current tenants who are part of an engagement.
    The list is sorted by department name, then by tenant name.
    This endpoint was implemented for the patches so Bene can write everyone that wants a badge for a department he did in the past. So this function is more of a onetime use and not implemented in the frontend. But it is kept in case we need it sometime in the future.
    """
    export_engagement_tenants_csv.required_groups = ['Netzwerkreferat', 'ADMIN']
    export_engagement_tenants_csv.required_employee_types = ['TENANT']

    today = timezone.now().date()

    # Query for engagements of current tenants, prefetching related objects for efficiency
    engagements = Engagement.objects.select_related(
        'tenant', 'department'
    ).filter(
        tenant__move_in__lte=today,
        tenant__move_out__gte=today
    ).order_by(
        'department__name', 'tenant__surname', 'tenant__name'
    )

    if not engagements.exists():
        return HttpResponse("No current tenants with engagements were found.", status=404)

    # Create the HttpResponse object with the appropriate CSV header.
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="current_engagement_tenants.csv"'},
    )
    response.write(u'\ufeff'.encode('utf8'))  # BOM for Excel UTF-8 compatibility

    writer = csv.writer(response)
    # Write the header row
    writer.writerow(['Department', 'Semester', 'Tenant Name', 'Tenant Surname', 'Email', 'Room'])

    # Write data rows
    for engagement in engagements:
        writer.writerow([
            engagement.department.name if engagement.department else 'N/A',
            engagement.semester,
            engagement.tenant.name,
            engagement.tenant.surname,
            engagement.tenant.email,
            engagement.tenant.current_room or 'N/A'
        ])

    return response


def _get_ldap_group_name_from_department(department_full_name, tenant):
    """Transforms a department full name into an LDAP group CN."""
    # Take first word if there's a space
    name = department_full_name.split(' ')[0]
    # Replace Umlauts
    name = name.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    
    #Special case for Flursprecher they also get assigned with the correct floor
    if name.lower() == 'flursprecher':
        if tenant.current_floor:
            name += f"-{tenant.current_floor}"
    print(name)
    return name

@transaction.atomic
@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def update_semester_and_ldap_view(request):
    """
    Updates the current semester and synchronizes LDAP groups for the old and new semester engagements.
    This is a critical, transactional operation.
    """
    update_semester_and_ldap_view.required_groups = ['Heimrat', 'ADMIN']
    
    new_semester = request.data.get('new_semester')
    if not new_semester or not checkValidSemesterFormat(new_semester):
        return Response({"error": "A valid 'new_semester' is required."}, status=status.HTTP_400_BAD_REQUEST)

    settings = GlobalAppSettings.load()
    old_semester = settings.current_semester
    
    if new_semester == old_semester:
        return Response({"message": "Semester is already set to the provided value. No action taken."}, status=status.HTTP_200_OK)

    group_base_dn = "ou=groups2,dc=schollheim,dc=net"
    ldap_errors = []

    # Remove tenants from old semester's engagement groups
    old_engagements = Engagement.objects.filter(semester=old_semester).select_related('tenant', 'department')
    logger.info(f"Found {old_engagements.count()} engagements in old semester '{old_semester}' to process for LDAP group removal.")
    for eng in old_engagements:
        if eng.tenant.username:
            group_cn = _get_ldap_group_name_from_department(eng.department.full_name, eng.tenant)
            group_dn = f"cn={group_cn},{group_base_dn}"
            success = ldap_utils.remove_user_from_group(eng.tenant.username, group_dn)
            if not success:
                ldap_errors.append(f"Failed to remove {eng.tenant.username} from {group_dn}")
            # Remove tenant from 'HSV' group as well
            hsv_group_dn = "cn=HSV,ou=groups2,dc=schollheim,dc=net"
            success_hsv = ldap_utils.remove_user_from_group(eng.tenant.username, hsv_group_dn)
            if not success_hsv:
                ldap_errors.append(f"Failed to remove {eng.tenant.username} from {hsv_group_dn}")

    # Add tenants to new semester's engagement groups
    new_engagements = Engagement.objects.filter(semester=new_semester).select_related('tenant', 'department')
    logger.info(f"Found {new_engagements.count()} engagements in new semester '{new_semester}' to process for LDAP group addition.")
    for eng in new_engagements:
        if eng.tenant.username:
            group_cn = _get_ldap_group_name_from_department(eng.department.full_name, eng.tenant)
            group_dn = f"cn={group_cn},{group_base_dn}"
            success = ldap_utils.add_user_to_group(eng.tenant.username, group_dn)
            if not success:
                ldap_errors.append(f"Failed to add {eng.tenant.username} to {group_dn}")
            # Also add tenant to 'HSV' group
            hsv_group_dn = "cn=HSV,ou=groups2,dc=schollheim,dc=net"
            success_hsv = ldap_utils.add_user_to_group(eng.tenant.username, hsv_group_dn)
            if not success_hsv:
                ldap_errors.append(f"Failed to add {eng.tenant.username} to {hsv_group_dn}")
            

    if ldap_errors:
        # The transaction will be rolled back automatically on exception.
        logger.error("LDAP synchronization failed. Rolling back transaction. Errors: " + "; ".join(ldap_errors))
        raise Exception("One or more LDAP operations failed. The semester has not been updated.")

    # Update the semester in the database
    settings.current_semester = new_semester
    settings.save()
    logger.info(f"Successfully updated semester from '{old_semester}' to '{new_semester}' and synchronized LDAP groups.")

    return Response({
        "message": f"Semester successfully updated to {new_semester}. LDAP groups synchronized.",
        "removed_from_groups_for_semester": old_semester,
        "added_to_groups_for_semester": new_semester
    })


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def export_tenants_csv(request):
    """
    API endpoint to export a CSV file of tenants.
    Filter by floor using query parameter: ?floor=H1EG or ?floor=all
    CSV format: "firstname","lastname","email","room_number"
    """
    export_tenants_csv.required_groups = ["Heimrat", "Inforeferat", "Zimmerreferat","Finanzenreferat","Schlichtungsreferat", "ADMIN"]
    
    floor = request.GET.get('floor', 'all')
    
    today = timezone.now().date()
    
    # Base queryset for current tenants
    tenants = Tenant.objects.filter(
        move_in__lte=today,
        move_out__gte=today
    )
    
    # Apply floor filter if not "all"
    if floor != 'all':
        tenants = tenants.filter(current_floor=floor)
    
    tenants = tenants.order_by('surname', 'name')
    
    if not tenants.exists():
        return HttpResponse("No tenants found for the specified filter.", status=404)
    
    # Create CSV response
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="tenants_floor_{floor}.csv"'},
    )
    response.write(u'\ufeff'.encode('utf8'))  # BOM for Excel UTF-8 compatibility
    
    writer = csv.writer(response)
    writer.writerow(['firstname', 'lastname', 'email', 'attribute_1'])
    
    for tenant in tenants:
        writer.writerow([
            tenant.name,
            tenant.surname,
            tenant.email,
            tenant.current_room or 'N/A'
        ])
    
    return response

# --- Derpartment Management ---
@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def list_departments_view(request):
    """
    Lists all departments.
    """
    list_departments_view.required_groups = ['Netzwerkreferat']

    departments = Department.objects.all().order_by('name')
    serializer = DepartmentSerializer(departments, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def create_department_view(request):
    """
    Creates a new department.
    """
    create_department_view.required_groups = ['Netzwerkreferat']

    serializer = NewDepartmentSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    max_id_result = Department.objects.aggregate(max_id=Max('id'))
    new_id = (max_id_result['max_id'] or 0) + 1

    department = Department.objects.create(
        id=new_id,
        name=serializer.validated_data['name'],
        full_name=serializer.validated_data['full_name'],
        points=serializer.validated_data['points'],
        size=serializer.validated_data['size']
    )
    response_serializer = DepartmentSerializer(department)
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)

@api_view(['PUT'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def update_department_view(request, department_id):
    """
    Updates an existing department.
    """
    update_department_view.required_groups = ['Netzwerkreferat']

    department = get_object_or_404(Department, id=department_id)
    serializer = DepartmentSerializer(department, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    department = serializer.save()
    response_serializer = DepartmentSerializer(department)
    return Response(response_serializer.data)

# ToDO: This is not completly correct yet. We need to check if there are engagements for this department first before deleting it. Now it will just fail and a user can only delete departments that dont have any engagement entries yet. But since this function isnt used often this is fine for now.
@api_view(['DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def delete_department_view(request, department_id):
    """
    Deletes a department.
    """
    delete_department_view.required_groups = ['Netzwerkreferat']

    department = get_object_or_404(Department, id=department_id)
    department.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# --- Misc Overview Endpoints ---

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def tenant_overview_data_view(request):
    """
    Retrieves a list of all current tenants, including their full details and all associated engagements.
    """
    tenant_overview_data_view.required_groups = ["Heimrat", "Inforeferat", "Zimmerreferat", "ADMIN"]
    today = timezone.now().date()
    
    # Prefetch engagements and their related departments to avoid N+1 queries
    tenants = Tenant.objects.filter(
        move_in__lte=today,
        move_out__gte=today
    ).prefetch_related(
        Prefetch(
            'engagement_set',
            queryset=Engagement.objects.select_related('department').order_by('-semester')
        )
    ).order_by('surname', 'name')

    serializer = TenantOverviewSerializer(tenants, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def tenant_statistics_view(request):
    """
    Returns aggregate statistics over tenants.

    Query parameter:
      ?scope=current  - only tenants currently living in the dorm (default)
      ?scope=all      - all tenants ever stored in the database
    """
    tenant_statistics_view.required_groups = HEIMRAT_INFO_GROUPS

    scope = request.GET.get('scope', 'current').lower()
    if scope not in ['current', 'all']:
        return Response(
            {"error": "Parameter 'scope' must be 'current' or 'all'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    today = timezone.now().date()

    if scope == 'current':
        base_qs = Tenant.objects.filter(move_in__lte=today, move_out__gte=today)
    else:
        base_qs = Tenant.objects.all()

    tenants_list = list(base_qs.values(
        'id', 'birthday', 'move_in', 'move_out',
        'gender', 'nationality', 'university', 'study_field',
        'current_points', 'current_floor'
    ))

    total = len(tenants_list)
    if total == 0:
        return Response({"scope": scope, "total_tenants": 0})

    def _avg(lst):
        return round(sum(lst) / len(lst), 2) if lst else None

    # --- Age ---
    ages = []
    for t in tenants_list:
        bd = t['birthday']
        if bd:
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            ages.append(age)

    # --- Stay duration (actual days lived so far / in total) ---
    stay_days = []
    for t in tenants_list:
        mi = t['move_in']
        mo = t['move_out']
        if mi:
            end = min(mo, today) if mo else today
            days = (end - mi).days
            if days >= 0:
                stay_days.append(days)

    avg_stay_days = _avg(stay_days)
    avg_stay_months = round(avg_stay_days / 30.44, 1) if avg_stay_days is not None else None

    # --- Gender distribution ---
    gender_counts = defaultdict(int)
    for t in tenants_list:
        gender_counts[(t['gender'] or 'Unbekannt').strip()] += 1

    # --- Nationality breakdown ---
    nationality_counts = defaultdict(int)
    for t in tenants_list:
        nationality_counts[(t['nationality'] or 'Unbekannt').strip()] += 1

    # --- University breakdown ---
    university_counts = defaultdict(int)
    for t in tenants_list:
        university_counts[(t['university'] or 'Unbekannt').strip()] += 1

    # --- Study field breakdown ---
    study_field_counts = defaultdict(int)
    for t in tenants_list:
        study_field_counts[(t['study_field'] or 'Unbekannt').strip()] += 1

    # --- Points ---
    points_values = [
        float(t['current_points'])
        for t in tenants_list
        if t['current_points'] is not None
    ]

    # --- Floor distribution ---
    floor_counts = defaultdict(int)
    for t in tenants_list:
        floor_counts[(t['current_floor'] or 'Unbekannt').strip()] += 1

    # --- Engagements per tenant ---
    tenant_ids = [t['id'] for t in tenants_list]
    eng_per_tenant_qs = (
        Engagement.objects
        .filter(tenant_id__in=tenant_ids)
        .values('tenant_id')
        .annotate(count=Count('id'))
    )
    eng_count_map = {row['tenant_id']: row['count'] for row in eng_per_tenant_qs}
    eng_counts_per_tenant = [eng_count_map.get(t['id'], 0) for t in tenants_list]
    tenants_with_any_engagement = sum(1 for c in eng_counts_per_tenant if c > 0)
    avg_engagements = _avg(eng_counts_per_tenant)

    response_data = {
        "scope": scope,
        "total_tenants": total,
        "age": {
            "average": _avg(ages),
            "min": min(ages) if ages else None,
            "max": max(ages) if ages else None,
        },
        "stay_duration": {
            "average_days": avg_stay_days,
            "average_months": avg_stay_months,
            "min_days": min(stay_days) if stay_days else None,
            "max_days": max(stay_days) if stay_days else None,
        },
        "gender_distribution": dict(
            sorted(gender_counts.items(), key=lambda x: -x[1])
        ),
        "nationalities": dict(
            sorted(nationality_counts.items(), key=lambda x: -x[1])
        ),
        "universities": dict(
            sorted(university_counts.items(), key=lambda x: -x[1])
        ),
        "study_fields": dict(
            sorted(study_field_counts.items(), key=lambda x: -x[1])
        ),
        "points": {
            "average": _avg(points_values),
            "min": min(points_values) if points_values else None,
            "max": max(points_values) if points_values else None,
            "total": round(sum(points_values), 2) if points_values else 0,
        },
        "floor_distribution": dict(
            sorted(floor_counts.items(), key=lambda x: x[0])
        ),
        "engagements": {
            "tenants_with_any_engagement": tenants_with_any_engagement,
            "tenants_without_engagement": total - tenants_with_any_engagement,
            "average_per_tenant": avg_engagements,
        },
    }

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def engagement_overview_data_view(request):
    """
    Retrieves all engagement entries, grouped by department.
    Each engagement includes minimal tenant info.
    """
    engagement_overview_data_view.required_groups = ["Heimrat", "Inforeferat", "Zimmerreferat","Finanzenreferat","Schlichtungsreferat", "ADMIN"]

    # Query all engagements with related data
    engagements_query = Engagement.objects.select_related(
        'tenant', 'department'
    ).order_by('department__name', '-semester', 'tenant__surname')
    
    # Group engagements by department
    grouped_engagements = defaultdict(lambda: {
        "department_id": None,
        "department_name": None,
        "department_full_name": None,
        "engagements": []
    })
    
    for engagement in engagements_query:
        dept_id = engagement.department.id
        group = grouped_engagements[dept_id]
        
        if group["department_id"] is None:
            group["department_id"] = dept_id
            group["department_name"] = engagement.department.name
            group["department_full_name"] = engagement.department.full_name
            
        # Serialize individual engagement
        engagement_serializer = AdminEngagementListSerializer(engagement)
        group["engagements"].append(engagement_serializer.data)
        
    # Convert the defaultdict to a simple list for the final response
    response_data = list(grouped_engagements.values())
    
    return Response(response_data, status=status.HTTP_200_OK)