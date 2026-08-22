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

def group_required(*groups):
    """
    Builds a permission class with the allowed groups baked into it.

    Use this instead of setting `required_groups` on the view function: @api_view returns
    the function produced by as_view(), so an attribute set on it never reaches the
    APIView instance that HasGroupPermission inspects - the requirement is silently
    ignored and the endpoint ends up open to every authenticated user.
    """
    allowed_groups = list(groups)

    class RequiredGroupsPermission(BasePermission):
        def has_permission(self, request, view):
            if not request.user or not request.user.is_authenticated:
                return False

            user_groups = [group.name for group in request.user.groups.all()]
            return any(group in user_groups for group in allowed_groups)

    return RequiredGroupsPermission

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
        
        employee_type = request.user.first_name  # We used first_name for employeeType in the LDAP mapping
        return employee_type in required_employee_types

# Combined permission class, I think these both checks are sufficient to cover all auth cases in smartdorm (?)
class GroupAndEmployeeTypePermission(HasGroupPermission, HasUserTypePermission):
    """
    Combines group and user type checks.
    """
    def has_permission(self, request, view):
        return HasGroupPermission.has_permission(self, request, view) and \
               HasUserTypePermission.has_permission(self, request, view)

# --- Subtenant permissions ---
# Built as real permission classes rather than declared via `required_employee_types`,
# which has no effect on @api_view endpoints for the same reason `required_groups`
# does not - see group_required() above.

class IsSubtenant(BasePermission):
    """Allows only accounts that belong to a subtenant."""

    def has_permission(self, request, view):
        from .utils.subtenant_utils import is_subtenant_account

        return is_subtenant_account(request.user)


class IsNotSubtenant(BasePermission):
    """
    Blocks subtenant accounts. Rarely needed on individual views - SubtenantApiGuardMiddleware
    already denies every API path that is not explicitly opened to subtenants.
    """

    def has_permission(self, request, view):
        from .utils.subtenant_utils import is_subtenant_account

        if not request.user or not request.user.is_authenticated:
            return False

        return not is_subtenant_account(request.user)
