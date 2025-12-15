# apps/users/permissions.py

from rest_framework import permissions

class IsVerifiedOrStaff(permissions.BasePermission):
    """
    Custom permission to only allow access to users whose account status is 'verified'.
    Admins/Staff are always allowed.
    """
    message = 'Access denied. You must have a Verified account status to perform this action.'

    def has_permission(self, request, view):
        # Allow staff/superuser access unconditionally
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        # Check if the user is authenticated (JWT passed)
        if request.user.is_authenticated:
            # CRITICAL CHECK: Status must be 'verified'
            return request.user.status == 'verified'
            
        return False