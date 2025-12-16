# apps/users/permissions.py 

from rest_framework import permissions

class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or staff users to edit/delete it.
    """
    message = 'You must be the owner of this object or an administrator to perform this action.'

    def has_object_permission(self, request, view, obj):
        # Allow read permissions (GET, HEAD, OPTIONS) for any authenticated user 
        # (Though we might use AllowAny on the view level for GET)
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner or staff/admin
        # 1. Check if the user is a staff/admin user
        if request.user and request.user.is_staff:
            return True
            
        # 2. Check if the user is the owner of the object (obj must have an 'owner' attribute)
        return obj.owner == request.user