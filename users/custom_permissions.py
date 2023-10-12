from rest_framework.permissions import IsAuthenticated, BasePermission, SAFE_METHODS

class ReadOnlyOrIsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        # Allow read permissions for all requests
        if request.method in SAFE_METHODS:
            return True

        # Check if the user is authenticated
        return request.user and request.user.is_authenticated