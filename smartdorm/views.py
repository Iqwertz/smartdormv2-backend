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
    """Class to handle PDF generation for engagement applications."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            'Title',
            parent=self.styles['Heading1'],
            alignment=TA_CENTER,
            spaceAfter=12
        )
        self.heading_style = self.styles['Heading2']
        self.normal_style = self.styles['Normal']

        self.pagesize = A4
        self.available_width = self.pagesize[0] - 2 * inch
        self.max_img_width = 2.5 * inch
        self.max_img_height = 3 * inch

    def resize_image(self, img_data, max_w, max_h):
        try:
            pil_img = PILImage.open(img_data)
            img_w, img_h = pil_img.size
            aspect = img_w / float(img_h)

            if img_w > img_h:
                final_w = min(max_w, max_w)
                final_h = final_w / aspect
                if final_h > max_h:
                    final_h = max_h
                    final_w = final_h * aspect
            else:
                final_h = min(max_h, max_h)
                final_w = final_h * aspect
                if final_w > max_w:
                    final_w = max_w
                    final_h = final_w / aspect

            return Image(img_data, width=final_w, height=final_h)
        except Exception as e:
            return Paragraph(f"Cannot display image: {e}", self.styles['Normal'])

    def create_application_element(self, application):
        elements = []

        elements.append(Paragraph(
            f"Bewerbung von {application.tenant.name} {application.tenant.surname} "
            f"für {application.department.name}",
            self.heading_style
        ))
        elements.append(Spacer(1, 0.2 * inch))

        text_content = Paragraph(application.motivation, self.normal_style)
        img_content = Spacer(1, 0.1 * inch)

        if application.image:
            img_content = self.resize_image(
                BytesIO(application.image),
                self.max_img_width,
                self.max_img_height
            )

        table_data = [[text_content, img_content]]
        col_widths = [self.available_width - self.max_img_width - 20, self.max_img_width]

        table = Table(table_data, colWidths=col_widths)
        # set the height of the image cell to be the same as the text
        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('RIGHTPADDING', (0, 0), (0, 0), 10),
            ('LEFTPADDING', (1, 0), (1, 0), 10),
            ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ]))

        elements.append(table)
        return elements

    def generate_pdf(self, applications, title="Bewerbungen - WS24/25"):
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=self.pagesize)

        elements = [
            Paragraph(title, self.title_style),
            Spacer(1, 0.5 * inch)
        ]

        for i, application in enumerate(applications):
            elements.extend(self.create_application_element(application))

            # each application is separated by a page break
            if i < len(applications) - 1:
                elements.append(PageBreak())
            else:
                elements.append(Spacer(1, 0.5 * inch))

        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()

        return pdf


def generate_applications_pdf(request):
    applications = EngagementApplication.objects.select_related('department', 'tenant').filter(semester="WS24/25")

    pdf_generator = PDFGenerator()
    pdf = pdf_generator.generate_pdf(applications)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="engagement_applications.pdf"'
    response.write(pdf)

    return response