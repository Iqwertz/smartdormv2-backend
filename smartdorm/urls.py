from django.urls import path, include
from django.views.generic import TemplateView

from .views.views import tenant_dashboard, TenantListCreateAPIView, TenantDetailAPIView
from .views import (
    auth_views,
    tenant_views,
    department_views,
    engagement_views,
    parcel_views,
    shared_views,
)

# Auth-related URLs
auth_urlpatterns = [
    path('login/', auth_views.login_view, name='api-login'),
    path('logout/', auth_views.logout_view, name='api-logout'),
    path('me/', auth_views.me_view, name='api-me'),
]

# Parcel-related URLs
parcel_urlpatterns = [
    path('create/', parcel_views.create_parcel_view, name='api-parcel-create'),
    path('list/', parcel_views.list_parcels_view, name='api-parcel-list'),
    path('<str:external_id>/pickup/', parcel_views.pickup_parcel_view, name='api-parcel-pickup'),
]

# Tenant-related URLs
tenant_urlpatterns = [
    path('profile-data/', tenant_views.profile_data_view, name='profile-data'),
    path('calendar-proxy/', tenant_views.calendar_proxy_view, name='calendar-proxy'),
    path('hsv/', tenant_views.hsv_engagement_list_view, name='hsv-engagement-list'),
    path('my-engagements/', tenant_views.my_engagements_view, name='my-engagements'),
    path('global-settings/', tenant_views.get_global_settings_view, name='global-settings'),
]

# Engagement-related URLs
engagement_urlpatterns = [
    path('heimrat/applications/', engagement_views.generate_applications_pdf, name='applications-pdf'),
    path('heimrat/set-semester/', engagement_views.set_current_semester_view, name='set-semester'),
    path('heimrat/set-applications-open/', engagement_views.set_applications_open_view, name='set-applications-open'),
    path('misc/export-engagement-tenants-csv/', engagement_views.export_engagement_tenants_csv, name='export-engagement-tenants-csv'),
]

# Department-related URLs
subtenant_urlpatterns = [
    path('list/', department_views.list_all_subtenants_view, name='subtenant-list-all'),
    path('create/', department_views.create_subtenant_view, name='subtenant-create'),
    path('<int:subtenant_id>/', department_views.get_subtenant_detail_view, name='subtenant-detail'),
    path('<int:subtenant_id>/update/', department_views.update_subtenant_view, name='subtenant-update'),
    path('<int:subtenant_id>/delete/', department_views.delete_subtenant_view, name='subtenant-delete'),
]

department_urlpatterns = [
    # Tenant management
    path('tenant-data/', department_views.all_tenant_data_view, name='department-tenant-data'),
    path('tenant-data/<int:tenant_id>/', department_views.get_tenant_detail_view, name='department-get-tenant'),
    path('tenant-data/<int:tenant_id>/update/', department_views.update_tenant_view, name='department-update-tenant'),
    path('tenant-data/<int:tenant_id>/delete/', department_views.delete_tenant_view, name='department-delete-tenant'),
    path('tenant-data/<int:tenant_id>/subtenants/', department_views.list_subtenants_for_tenant_view, name='department-list-subtenants'),
    path('create-new-tenant/', department_views.create_new_tenant_view, name='department-create-new-tenant'),
    # Subtenant management
    path('subtenants/', include(subtenant_urlpatterns)),
    path('parcels/', include(parcel_urlpatterns)),
]

# Admin-related URLs
admin_urlpatterns = [
    path('', TenantListCreateAPIView.as_view(), name='tenant-list-create'),
    path('<int:pk>/', TenantDetailAPIView.as_view(), name='tenant-detail'),
]

# Shared/common URLs
common_urlpatterns = [
    path('tenant-list/', shared_views.tenants_for_select_view, name='department-tenants-for-select'),
    path('room-list/', shared_views.rooms_for_select_view, name='common-rooms-for-select'),
]

urlpatterns = [
    path('', TemplateView.as_view(template_name="home.html")),
    path('tenant-dashboard/', tenant_dashboard, name='tenant_dashboard'),

    path('api/auth/', include((auth_urlpatterns, 'auth'))),
    path('api/tenants/', include((tenant_urlpatterns, 'tenants'))),
    path('api/engagements/', include((engagement_urlpatterns, 'engagements'))),
    path('api/department/', include((department_urlpatterns, 'department'))),
    path('api/admin/', include((admin_urlpatterns, 'admin'))),
    path('api/common/', include((common_urlpatterns, 'common'))),
]