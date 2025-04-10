from django.urls import path, include
from django.views.generic import TemplateView
from .views import tenant_dashboard, TenantListCreateAPIView, TenantDetailAPIView
from . import auth_views 
from .tenant_views import profile_data_view

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
    
    path('api/tenants/profile-data', profile_data_view, name='profile-data'),
    
    path('api/auth/', include(auth_urlpatterns)),
]