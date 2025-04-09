# Here we want to define all functions that handle the permission logic for the endpoints.

from rest_framework.permissions import BasePermission

class HasGroupPermission(BasePermission):
    """
    Ensures the user is in one of the required groups. If no groups are specified, all are allowed.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get required_groups from view, default to empty list
        required_groups = getattr(view, 'required_groups', [])
        if not required_groups:  # If empty, allow all groups
            return True
        
        user_groups = [group.name for group in request.user.groups.all()]
        return any(group in user_groups for group in required_groups)

class HasUserTypePermission(BasePermission):
    """
    Ensures the user has one of the required user types. Mostly used to differentiate between Tenant and Verwaltung, but could be used to handle subtenants as well...
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        required_employee_types = getattr(view, 'required_employee_types', [])
        if not required_employee_types:  # If empty, no employeeType restriction
            return True
        
        employee_type = request.user.user_type
        return employee_type in required_employee_types

# Combined permission class, I think these both checks are sufficient to cover all auth cases in smartdorm (?)
class GroupAndEmployeeTypePermission(HasGroupPermission, HasUserTypePermission):
    """
    Combines group and user type checks.
    """
    def has_permission(self, request, view):
        return HasGroupPermission.has_permission(self, request, view) and \
               HasUserTypePermission.has_permission(self, request, view)