#In this file we have all views that are in some way restricted to a engagement role
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication

from ..permissions import GroupAndEmployeeTypePermission
from ..models import EngagementApplication, GlobalAppSettings
from ..serializers import GlobalAppSettingsSerializer
from rest_framework.response import Response
from rest_framework import status

from io import BytesIO
from PIL import Image as PILImage

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
    semester_filter = request.GET.get('semester', settings.current_semester) # Example: get semester from query param or default
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
    if not new_semester or not isinstance(new_semester, str):
        return Response(
            {"error": "Field 'current_semester' is required and must be a string."},
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