# views.py #@Yassin didnt update this file, I think we want to group all tenant related views into the tenant_views.py and all "Verwaltungs" views into admin_views.py or? If so we then need to use the new permission management like i have wrote down in the auth_views.py at the bottom. 
from django.shortcuts import render, get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from smartdorm.models import (
    Tenant,
    get_tenants_by_university, 
    get_active_tenants, 
    get_tenant_details, 
    get_expiring_probations,
    EngagementApplication,
)
from .models import Tenant
from smartdorm.serializers import TenantSerializer

from django.contrib.auth import login, logout
from django_auth_ldap.backend import LDAPBackend
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

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

def tenant_dashboard(request):
    # Get all the data
    context = {
        'active_tenants': get_active_tenants(),
        'university_tenants': get_tenants_by_university('Example University'),
        'tenant_details': get_tenant_details(tenant_id=1),
        'expiring_probations': get_expiring_probations(days_threshold=15)
    }
    
    return render(request, 'tenants.html', context)

class TenantListCreateAPIView(APIView):
    """
    API view to create a new tenant or list all tenants
    """
    def get(self, request):
        tenants = Tenant.objects.all()
        serializer = TenantSerializer(tenants, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = TenantSerializer(data=request.data)
        if serializer.is_valid():
            # The model has managed=False, so we need to save manually
            # and generate an ID since it's not auto-incrementing
            try:
                # Generate a new ID by getting the max ID and adding 1
                max_id = Tenant.objects.all().order_by('-id').first()
                new_id = 1 if max_id is None else max_id.id + 1
                
                # Create the tenant with the new ID
                tenant_data = serializer.validated_data
                tenant = Tenant.objects.create(
                    id=new_id,
                    **tenant_data
                )
                
                # Return the serialized tenant data
                return Response(
                    TenantSerializer(tenant).data, 
                    status=status.HTTP_201_CREATED
                )
            except Exception as e:
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TenantDetailAPIView(APIView):
    """
    API view to retrieve, update or delete a tenant
    """
    def get(self, request, pk):
        tenant = get_object_or_404(Tenant, pk=pk)
        serializer = TenantSerializer(tenant)
        return Response(serializer.data)

    def put(self, request, pk):
        tenant = get_object_or_404(Tenant, pk=pk)
        serializer = TenantSerializer(tenant, data=request.data)
        if serializer.is_valid():
            # Update fields manually since managed=False
            for attr, value in serializer.validated_data.items():
                setattr(tenant, attr, value)
            tenant.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        tenant = get_object_or_404(Tenant, pk=pk)
        tenant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def login_view(request):
    error_message = None
    success_message = None

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        try:
            ldap_backend = LDAPBackend()
            user = ldap_backend.authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user, backend='django_auth_ldap.backend.LDAPBackend')

                return JsonResponse({
                    "success": True,
                    "message": f"You are logged in as {user.username}",
                    "user": {
                        "username": user.username,
                        "email": user.email
                    }
                })
            else:
                return JsonResponse({
                    "success": False,
                    "message": "Authentication failed. Invalid credentials."
                }, status=401)
        except Exception as e:
            return JsonResponse({
                "success": False,
                "message": f"Error: {str(e)}"
            }, status=500)

    # For GET requests, return status information
    elif request.method == 'GET':
        if request.user.is_authenticated:
            return JsonResponse({
                "success": True,
                "message": f"User is already authenticated as {request.user.username}",
                "user": {
                    "username": request.user.username,
                    "email": request.user.email
                }
            })
        else:
            return JsonResponse({
                "success": False,
                "message": "Not authenticated"
            })

    return JsonResponse({
        "success": False,
        "message": "Method not allowed"
    }, status=405)


@csrf_exempt
def logout_view(request):
    logout(request)
    return JsonResponse({"success": True, "message": "Successfully logged out"})


def me_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({
            "authenticated": False,
            "message": "Not authenticated"
        }, status=401)

    user = request.user

    return JsonResponse({
        "authenticated": True,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_staff": user.is_staff,
        "last_login": user.last_login.isoformat() if user.last_login else None
    })


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

# @api_view(['GET']) # Uncomment if using DRF function-based view
# @permission_classes([IsAuthenticated]) # Add appropriate permissions
def generate_applications_pdf(request):
    # Fetch applications, prefetch related tenant and department for efficiency
    # Adjust the filter as needed (e.g., specific semester)
    semester_filter = request.GET.get('semester', 'WS24/25') # Example: get semester from query param or default
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
