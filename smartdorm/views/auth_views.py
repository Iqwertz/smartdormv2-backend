import json
import secrets
import string
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.middleware.csrf import get_token
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status
from pprint import pprint
from django.contrib.auth.models import User
from ..models import Tenant
from ..utils.email_utils import send_email_message
from ..utils.ldap_utils import update_ldap_password
import logging

logger = logging.getLogger(__name__)

# Helper function to build the user data object
def get_user_data(user):
    if not user or not user.is_authenticated:
        return None
    group_names = [group.name for group in user.groups.all()]
    return {
        "username": user.username,
        "name": user.first_name,
        "surname": user.last_name,
        "email": user.email,
        "groups": group_names,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "user_type": user.first_name #Tenant or Verwaltung, uses first_name field for employeeType (see settings.py)
    }

@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([SessionAuthentication]) # Use session auth
def login_view(request):
    try:
        username = request.data.get('username')
        password = request.data.get('password')
        remember_me = request.data.get('rememberMe', False)
    except json.JSONDecodeError:
        return Response({"success": False, "message": "Invalid JSON data"}, status=status.HTTP_400_BAD_REQUEST)

    if not username or not password:
        return Response({"success": False, "message": "Username and password required"}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(request, username=username, password=password)

    if user is not None:
        # Regenerate session ID on login
        auth_login(request, user)

        if remember_me:
            # Use the long expiry defined in settings.SESSION_COOKIE_AGE
            request.session.set_expiry(None)
        else:
            # Expire session when browser closes
            request.session.set_expiry(0)

        user_data = get_user_data(user)
        if user_data:
             # response_data = {"success": True, "user": user_data, "csrfToken": get_token(request)}
             response_data = {"success": True, "user": user_data}
             return Response(response_data, status=status.HTTP_200_OK)
        else:
             return Response({"success": False, "message": "Login successful but failed to retrieve user data."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response({"success": False, "message": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def logout_view(request):
    auth_logout(request)
    return Response({"success": True, "message": "Successfully logged out"}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def me_view(request):
    user_data = get_user_data(request.user)
    if user_data:
        return Response({"authenticated": True, "user": user_data}, status=status.HTTP_200_OK)
    else:
        return Response({"authenticated": False, "message": "User authenticated but data unavailable"}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([SessionAuthentication])
def password_reset_view(request):
    """
    Reset password for a user by email.
    Generates a new 12-character password, updates it in LDAP, and sends it via email.
    """
    try:
        email = request.data.get('email')
        if not email:
            return Response(
                {"success": False, "message": "Email address is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generate a secure 12-character password
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        new_password = ''.join(secrets.choice(alphabet) for _ in range(12))

        # Find user by email
        try:
            user = User.objects.get(email=email)
            
            try:
                tenant = Tenant.objects.get(email=email)
                greeting = tenant.name  
            except Tenant.DoesNotExist:
                greeting = user.username  # Fallback
                
        except User.DoesNotExist:
            # Don't reveal if email exists or not for security
            return Response(
                {"success": True, "message": "If the email address exists, a password reset email has been sent."}, 
                status=status.HTTP_200_OK
            )

        # Update password in LDAP
        try:
            update_ldap_password(user.username, new_password)
        except Exception as e:
            logger.error(f"Failed to update LDAP password for user {user.username}: {e}")
            return Response(
                {"success": False, "message": "Failed to reset password. Please contact support."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Send email with new password
        email_context = {
            'greeting': greeting,
            'username': user.username,
            'password': new_password,
        }

        email_sent = send_email_message(
            recipient_list=[email],
            subject="SmartDorm - Passwort zurückgesetzt",
            html_template_name="email/user-password-reset.html",
            context=email_context
        )

        if email_sent:
            return Response(
                {"success": True, "message": "Password reset email sent successfully."}, 
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"success": False, "message": "Failed to send password reset email. Please contact support."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    except Exception as e:
        logger.error(f"Password reset error: {e}")
        return Response(
            {"success": False, "message": "An error occurred during password reset."}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def password_change_view(request):
    """
    Change password for authenticated user.
    Requires old password verification and new password confirmation.
    """
    try:
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')
        
        if not old_password or not new_password or not confirm_password:
            return Response(
                {"success": False, "message": "Alle Felder sind erforderlich."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if new_password != confirm_password:
            return Response(
                {"success": False, "message": "Die neuen Passwörter stimmen nicht überein."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(new_password) < 8:
            return Response(
                {"success": False, "message": "Das neue Passwort muss mindestens 8 Zeichen lang sein."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify old password
        user = authenticate(request, username=request.user.username, password=old_password)
        if user is None:
            return Response(
                {"success": False, "message": "Das aktuelle Passwort ist falsch."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update password in LDAP
        try:
            update_ldap_password(request.user.username, new_password)
            logger.info(f"Password successfully changed for user: {request.user.username}")
            return Response(
                {"success": True, "message": "Passwort erfolgreich geändert."}, 
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Failed to update LDAP password for user {request.user.username}: {e}")
            return Response(
                {"success": False, "message": "Fehler beim Ändern des Passworts. Bitte versuchen Sie es später erneut."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    except Exception as e:
        logger.error(f"Password change error: {e}")
        return Response(
            {"success": False, "message": "Ein Fehler ist aufgetreten."}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# --- Example Protected View ---
#
# Tenant dashboard: Specific groups and employee type
#@api_view(['GET'])
#@permission_classes([IsAuthenticated, GroupAndEmployeeTypePermission])
#@authentication_classes([SessionAuthentication])
#def netzwerk_dashboard_view(request):
#    tenant_dashboard_view.required_groups = ['Netzwerkreferat']
#    tenant_dashboard_view.required_employee_types = ['TENANT']
#    return Response({"message": "Welcome to the netwerk dashboard!"})