# Django URLs

from django.urls import path
from django.views.generic import TemplateView

from django.conf import settings
from smartdorm.views import tenant_dashboard, TenantListCreateAPIView, TenantDetailAPIView, login_view

urlpatterns = [
    path('', TemplateView.as_view(template_name="home.html")),
    path('tenant-dashboard/', tenant_dashboard, name='tenant_dashboard'),
    
    # API endpoints
    path('api/tenants/', TenantListCreateAPIView.as_view(), name='tenant-list-create'),
    path('api/tenants/<int:pk>/', TenantDetailAPIView.as_view(), name='tenant-detail'),
    path('api/login/', login_view, name='api-login'),
]
