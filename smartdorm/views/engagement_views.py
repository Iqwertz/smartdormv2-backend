#In this file we have all views that are in some way restricted to a engagement role
from django.http import HttpResponse
from django.utils import timezone
from django.urls import reverse
from rest_framework.decorators import api_view, permission_classes, authentication_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Max
import uuid
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.db import transaction

from ..utils.helper import checkValidSemesterFormat, get_next_semester
from ..permissions import GroupAndEmployeeTypePermission
from ..models import EngagementApplication, GlobalAppSettings, Engagement, Tenant, Department
from ..serializers import (
    GlobalAppSettingsSerializer, EngagementApplicationListSerializer,
    HeimratEngagementApplicationCreateSerializer, AdminEngagementListSerializer,
    EngagementCreateByHeimratSerializer, EngagementPointUpdateSerializer
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

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def generate_applications_pdf(request):
    
    generate_applications_pdf.required_groups = ['Netzwerkreferat', 'Heimrat', 'ADMIN']
    generate_applications_pdf.required_employee_types = ['TENANT']
    # Fetch applications, prefetch related tenant and department for efficiency
    # Adjust the filter as needed (e.g., specific semester)
    settings = GlobalAppSettings.load()
    semester_filter = request.GET.get('semester', get_next_semester(settings.current_semester)) # Example: get semester from query param or default
    applications = EngagementApplication.objects.select_related(
        'department', 'tenant'
    ).filter(
        semester=semester_filter
    ).order_by( # Order ensures predictable grouping if needed later, but grouping handles it
        'department__name', 'tenant__surname', 'tenant__name'
    )

    if not applications.exists():
         return HttpResponse(f"Keine Bewerbungen für das Semester {semester_filter} gefunden.", status=404)

    pdf_generator = PDFGenerator()
    pdf_title = f"Referatsbewerbungen - {semester_filter}"
    pdf = pdf_generator.generate_pdf(applications, title=pdf_title)

    response = HttpResponse(content_type='application/pdf')
    # Make filename dynamic based on semester
    response['Content-Disposition'] = f'attachment; filename="referatsbewerbungen_{semester_filter.replace("/", "-")}.pdf"'
    response.write(pdf)

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
        application.delete()
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
    
    response_serializer = AdminEngagementListSerializer(engagement)
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)

@api_view(['PUT'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
def update_engagement_points_view(request, engagement_id):
    """ Updates the points for a specific engagement. """
    update_engagement_points_view.required_groups = HEIMRAT_INFO_GROUPS
    
    engagement = get_object_or_404(Engagement, id=engagement_id)
    serializer = EngagementPointUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    engagement.points = serializer.validated_data['points']
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
    engagement.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
@transaction.atomic
def compensate_all_engagements_view(request):
    """ Sets all uncompensated engagements to compensated. """
    compensate_all_engagements_view.required_groups = HEIMRAT_INFO_GROUPS
    
    updated_count = Engagement.objects.filter(compensate=False).update(compensate=True)
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


def _get_ldap_group_name_from_department(department_full_name):
    """Transforms a department full name into an LDAP group CN."""
    # Take first word if there's a space
    name = department_full_name.split(' ')[0]
    # Replace Umlauts and make lowercase
    name = name.lower().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
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
            group_cn = _get_ldap_group_name_from_department(eng.department.full_name)
            group_dn = f"cn={group_cn},{group_base_dn}"
            success = ldap_utils.remove_user_from_group(eng.tenant.username, group_dn)
            if not success:
                ldap_errors.append(f"Failed to remove {eng.tenant.username} from {group_dn}")

    # Add tenants to new semester's engagement groups
    new_engagements = Engagement.objects.filter(semester=new_semester).select_related('tenant', 'department')
    logger.info(f"Found {new_engagements.count()} engagements in new semester '{new_semester}' to process for LDAP group addition.")
    for eng in new_engagements:
        if eng.tenant.username:
            group_cn = _get_ldap_group_name_from_department(eng.department.full_name)
            group_dn = f"cn={group_cn},{group_base_dn}"
            success = ldap_utils.add_user_to_group(eng.tenant.username, group_dn)
            if not success:
                ldap_errors.append(f"Failed to add {eng.tenant.username} to {group_dn}")

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