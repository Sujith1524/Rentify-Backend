# apps/users/permissions.py

from rest_framework import permissions

class IsVerifiedOrStaff(permissions.BasePermission):
    """
    Custom permission to only allow access to users whose account status is 'verified'.
    """
    message = 'Access denied. Account status must be Verified to access this feature.'

    def has_permission(self, request, view):
        user = request.user
        
        # 1. Allow staff/superuser access unconditionally (Admin review/management)
        if user.is_staff or user.is_superuser:
            return True
        
        # 2. Check for authenticated user and 'verified' status
        if user.is_authenticated:
            # The status we set after our (future) admin review endpoint approves
            return user.status == 'verified'
            
        return False