from django.urls import path, include
from django.views.generic import TemplateView

from .views import tenant_dashboard, TenantListCreateAPIView, TenantDetailAPIView
from . import auth_views 
from . import tenant_views
from . import department_views
from . import engagement_views
from . import parcel_views

# Group auth related URLs under /api/auth/
auth_urlpatterns = [
    path('login/', auth_views.login_view, name='api-login'),
    path('logout/', auth_views.logout_view, name='api-logout'),
    path('me/', auth_views.me_view, name='api-me'),
]

parcel_urlpatterns = [
    path('create/', parcel_views.create_parcel_view, name='api-parcel-create'),
    path('list/', parcel_views.list_parcels_view, name='api-parcel-list'),
    path('<str:external_id>/pickup/', parcel_views.pickup_parcel_view, name='api-parcel-pickup'),
]

urlpatterns = [
    path('', TemplateView.as_view(template_name="home.html")),
    path('tenant-dashboard/', tenant_dashboard, name='tenant_dashboard'),
    
    path('api/admin/', TenantListCreateAPIView.as_view(), name='tenant-list-create'), #@Yassin Moved your tenant endpoint to /api/admin/ since create and delete will be a only admin task
    path('api/admin/<int:pk>/', TenantDetailAPIView.as_view(), name='tenant-detail'),
    
    # Tenant Specific Views
    path('api/tenants/profile-data', tenant_views.profile_data_view, name='profile-data'),
    path('api/tenants/calendar-proxy', tenant_views.calendar_proxy_view, name='calendar-proxy'), # Used to fetch the ICS calendar file from Nextcloud
    path('api/tenants/hsv', tenant_views.hsv_engagement_list_view, name='hsv-engagement-list'),
    path('api/tenants/my-engagements', tenant_views.my_engagements_view, name='my-engagements'),    
    path('api/tenants/global-settings', tenant_views.get_global_settings_view, name='global-settings'),

    # Engagement Specific Views
    path('api/engagements/heimrat/applications/', engagement_views.generate_applications_pdf, name='applications-pdf'), #Generate PDF for all applications in a certain semester
    path('api/engagements/heimrat/set-semester/', engagement_views.set_current_semester_view, name='set-semester'), 
    path('api/engagements/heimrat/set-applications-open/', engagement_views.set_applications_open_view, name='set-applications-open'), 

    # Department Specific Views
    path('api/department/tenant-data', department_views.all_tenant_data_view, name='department-tenant-data'), 
    path('api/department/parcels/', include(parcel_urlpatterns)), 
    
    path('api/auth/', include(auth_urlpatterns)),
]