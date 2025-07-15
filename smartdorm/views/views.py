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
from ..models import Tenant
from smartdorm.serializers import TenantSerializer

from django.contrib.auth import login, logout
from django_auth_ldap.backend import LDAPBackend
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404



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



