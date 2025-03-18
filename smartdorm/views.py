# views.py
from django.shortcuts import render, get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view

from smartdorm.models import (
    Tenant,
    get_tenants_by_university, 
    get_active_tenants, 
    get_tenant_details, 
    get_expiring_probations
)
from smartdorm.serializers import TenantSerializer

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