from django.urls import path, include
from django.views.generic import TemplateView
from .views import tenant_dashboard, TenantListCreateAPIView, TenantDetailAPIView
from . import auth_views 
from . import tenant_views
from . import department_views

# Group auth related URLs under /api/auth/
auth_urlpatterns = [
    path('login/', auth_views.login_view, name='api-login'),
    path('logout/', auth_views.logout_view, name='api-logout'),
    path('me/', auth_views.me_view, name='api-me'),
]

urlpatterns = [
    path('', TemplateView.as_view(template_name="home.html")),
    path('tenant-dashboard/', tenant_dashboard, name='tenant_dashboard'),
    
    path('api/admin/', TenantListCreateAPIView.as_view(), name='tenant-list-create'), #@Yassin Moved your tenant endpoint to /api/admin/ since create and delete will be a only admin task
    path('api/admin/<int:pk>/', TenantDetailAPIView.as_view(), name='tenant-detail'),
    
    # Tenant Specific Views
    path('api/tenants/profile-data', tenant_views.profile_data_view, name='profile-data'),
    path('api/tenants/calendar-proxy', tenant_views.calendar_proxy_view, name='calendar-proxy'), # Used to fetch the ICS calendar file from Nextcloud
    path('api/tenants/my-engagements', tenant_views.my_engagements_view, name='my-engagements'),

    # Department Specific Views
    path('api/department/tenant-data', department_views.all_tenant_data_view, name='department-tenant-data'), 
    
    path('api/auth/', include(auth_urlpatterns)),
]