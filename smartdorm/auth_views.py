import json
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.middleware.csrf import get_token
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework import status

# Helper function to build the user data object
def get_user_data(user):
    if not user or not user.is_authenticated:
        return None

    # Get group names directly from the user object populated by django-auth-ldap
    group_names = [group.name for group in user.groups.all()]

    # Determine primary role of the user
    primary_role = None
    if "VERWALTUNG" in group_names:
        primary_role = "admin"
    elif "tenant" in group_names:
         primary_role = "tenant"
    # We may need to do some more fine-grained role checking here in the future

    return {
        "username": user.username,
        "name": user.first_name,
        "surname": user.last_name,
        "email": user.email,
        "groups": group_names,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "primary_role": primary_role 
    }

@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([SessionAuthentication]) # Use session auth
def login_view(request):
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        remember_me = data.get('rememberMe', False)
    except json.JSONDecodeError:
        return Response({"success": False, "message": "Invalid JSON data"}, status=status.HTTP_400_BAD_REQUEST)

    if not username or not password:
        return Response({"success": False, "message": "Username and password required"}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(request, username=username, password=password)

    if user is not None:
        # Regenerate session ID on login (good pactice to prevent session fixation attacks)
        auth_login(request, user)

        # Handle "Remember Me"
        if remember_me:
            # Use the long expiry defined in settings.SESSION_COOKIE_AGE
            request.session.set_expiry(None)
        else:
            # Expire session when browser closes
            request.session.set_expiry(0)

        user_data = get_user_data(user)
        if user_data:
             # Include CSRF token in response if needed by frontend for subsequent POST/PUT/DELETE
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

# --- Example Protected View ---
# from rest_framework.permissions import BasePermission
#
# class HasGroupPermission(BasePermission):
#     """
#     Ensures the user is in a required group.
#     """
#     required_groups = []
#
#     def has_permission(self, request, view):
#         if not request.user or not request.user.is_authenticated:
#             return False
#         user_groups = [group.name for group in request.user.groups.all()]
#         return any(group in user_groups for group in self.required_groups)
#
# class IsVerwaltungUser(HasGroupPermission):
#      required_groups = ['VERWALTUNG', 'ADMIN'] # Allow Verwaltung or ADMIN
#
# @api_view(['GET'])
# @permission_classes([IsAuthenticated, IsVerwaltungUser]) # Must be logged in AND in VERWALTUNG/ADMIN group
# @authentication_classes([SessionAuthentication])
# def admin_only_data(request):
#     # This view is only accessible to users in the 'VERWALTUNG' or 'ADMIN' group
#     return Response({"message": "Secret admin data!"})