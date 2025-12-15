# apps/listings/views.py

from rest_framework import generics, permissions
from apps.users.permissions import IsVerifiedOrStaff # Import our custom permission
from .models import Property
from .serializers import PropertyCreateSerializer

class PropertyListCreateAPIView(generics.ListCreateAPIView):
    """
    GET: List all approved properties (for public search).
    POST: Create a new property listing (Requires Verified KYC status).
    """
    queryset = Property.objects.filter(is_active=True, is_approved=True)
    serializer_class = PropertyCreateSerializer

    def get_permissions(self):
        # Apply the strict permission only to the creation (POST) method
        if self.request.method == 'POST':
            # User Story 3: Access Restriction Prior to Verification
            return [permissions.IsAuthenticated(), IsVerifiedOrStaff()]
        # Allow anonymous viewing for the list (GET) method
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        # Attach the current authenticated user as the owner
        serializer.save(owner=self.request.user)