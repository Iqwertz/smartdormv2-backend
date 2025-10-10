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
    path('my-departure/', tenant_views.my_departure_view, name='my-departure'),
    path('my-departure/decide/', tenant_views.decide_departure_view, name='decide-departure'),
    path('engagement-application/', tenant_views.create_engagement_application_view, name='create-engagement-application'),
    path('engagement-application/<int:app_id>/delete/', tenant_views.delete_engagement_application_view, name='delete-engagement-application'),
    path('engagement-application/<int:app_id>/image/', tenant_views.get_application_image_view, name='get-application-image'),
    path('engagement-applications/', tenant_views.list_engagement_applications_view, name='list-engagement-applications'),
    path('engagement-applications/pdf/', engagement_views.get_applications_pdf, name='applications-pdf'),
    path('my-engagement-applications/', tenant_views.my_engagement_applications_view, name='my-engagement-applications'),
]

# Engagement-related URLs
engagement_urlpatterns = [
    # Application Management for Heimrat
    path('heimrat/applications/list/', engagement_views.heimrat_list_applications_view, name='heimrat-list-applications'),
    path('heimrat/applications/create/', engagement_views.heimrat_create_application_view, name='heimrat-create-application'),
    path('heimrat/applications/<int:app_id>/delete/', engagement_views.heimrat_delete_application_view, name='heimrat-delete-application'),
    path('heimrat/applications/<int:app_id>/image/', engagement_views.heimrat_get_application_image_view, name='heimrat-get-application-image'),

    # Engagement Management for Heimrat/Inforeferat
    path('heimrat/engagements/list/', engagement_views.list_engagements_admin_view, name='admin-list-engagements'),
    path('heimrat/engagements/create/', engagement_views.create_engagement_admin_view, name='admin-create-engagement'),
    path('heimrat/engagements/<int:engagement_id>/update/', engagement_views.update_engagement_view, name='admin-update-engagement-points'),
    path('heimrat/engagements/<int:engagement_id>/delete/', engagement_views.delete_engagement_view, name='admin-delete-engagement'),
    path('heimrat/engagements/<int:engagement_id>/toggle-compensate/', engagement_views.toggle_engagement_compensate_view, name='admin-toggle-engagement-compensate'),
    path('heimrat/engagements/compensate-all/', engagement_views.compensate_all_engagements_view, name='admin-compensate-all'),

    # Tenant Data
    path('heimrat/export_tenants-csv/', engagement_views.export_tenants_csv, name='export-tenants-csv'),

    # Settings for Heimrat
    path('heimrat/set-semester/', engagement_views.set_current_semester_view, name='set-semester'),
    path('heimrat/update-semester-and-ldap/', engagement_views.update_semester_and_ldap_view, name='update-semester-and-ldap'),
    path('heimrat/set-applications-open/', engagement_views.set_applications_open_view, name='set-applications-open'),
    path('heimrat/set-show-applications/', engagement_views.set_show_applications_view, name='set-show-applications'),
    path('misc/export-engagement-tenants-csv/', engagement_views.export_engagement_tenants_csv, name='export-engagement-tenants-csv'),
    path('misc/tenant-overview-data/', engagement_views.tenant_overview_data_view, name='misc-tenant-overview-data'),
    path('misc/engagement-overview-data/', engagement_views.engagement_overview_data_view, name='misc-engagement-overview-data'),
]


# Department-related URLs
subtenant_urlpatterns = [
    path('list/', department_views.list_subtenants_view, name='subtenant-list-all'),
    path('create/', department_views.create_subtenant_view, name='subtenant-create'),
    path('<int:subtenant_id>/', department_views.get_subtenant_detail_view, name='subtenant-detail'),
    path('<int:subtenant_id>/update/', department_views.update_subtenant_view, name='subtenant-update'),
    path('<int:subtenant_id>/delete/', department_views.delete_subtenant_view, name='subtenant-delete'),
]

departure_management_urlpatterns = [
    path('candidates/', department_views.list_departure_candidates_view, name='departure-candidates'),
    path('create/', department_views.create_departure_view, name='departure-create'),
    path('list/', department_views.list_departures_view, name='departure-list'),
    path('<int:departure_id>/remind/', department_views.send_departure_reminder_view, name='departure-remind'),
    path('<int:departure_id>/close/', department_views.close_departure_view, name='departure-close'),
    path('<int:departure_id>/download-pdf/', department_views.download_departure_pdf_view, name='departure-download-pdf'),
]

department_signature_urlpatterns = [
    path('<str:department_slug>/list/', department_views.list_department_signatures_view, name='department-signature-list'),
    path('<int:signature_id>/update/', department_views.update_department_signature_view, name='department-signature-update'),
]

claim_management_urlpatterns = [
    path('list/', department_views.list_claims_view, name='claim-list'),
    path('<int:claim_id>/remind/', department_views.send_claim_reminder_view, name='claim-remind'),
    path('<int:claim_id>/status/', department_views.update_claim_status_view, name='claim-update-status'),
    path('<int:claim_id>/decide/', department_views.process_claim_decision_view, name='claim-decide'),
]


department_urlpatterns = [
    # Tenant management
    path('tenant-data/', department_views.all_tenant_data_view, name='department-tenant-data'),
    path('tenant-data/<int:tenant_id>/', department_views.get_tenant_detail_view, name='department-get-tenant'),
    path('tenant-data/<int:tenant_id>/update/', department_views.update_tenant_view, name='department-update-tenant'),
    path('tenant-data/<int:tenant_id>/delete/', department_views.delete_tenant_view, name='department-delete-tenant'),
    path('tenant-data/<int:tenant_id>/subtenants/', department_views.list_subtenants_for_tenant_view, name='department-list-subtenants'),
    path('tenant-data/<int:tenant_id>/rentals/', department_views.list_tenant_rentals_view, name='department-list-rentals'),
    path('tenant-data/<int:tenant_id>/move/', department_views.move_tenant_view, name='department-move-tenant'),
    path('create-new-tenant/', department_views.create_new_tenant_view, name='department-create-new-tenant'),
    # Subtenant management
    path('subtenants/', include(subtenant_urlpatterns)),
    path('parcels/', include(parcel_urlpatterns)),
    # Department Signatures
    path('signatures/', include(department_signature_urlpatterns)),
    # Departure Management
    path('departures/', include(departure_management_urlpatterns)),
    # Claim (Extension) Management
    path('claims/', include(claim_management_urlpatterns)),
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
    path('departments-for-select/', shared_views.departments_for_select_view, name='common-departments-for-select'),
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