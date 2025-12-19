# apps/listings/views.py

from rest_framework import generics, permissions, status
from apps.users.permissions import IsVerifiedOrStaff
from rest_framework.response import Response
from .models import Property
from rest_framework.views import APIView
from rest_framework.response import Response
from .services import ListingLocationService
from .serializers import ListingSerializer
from .serializers import PropertyCreateSerializer, PropertyReadSerializer, PropertyUpdateSerializer
from apps.listings.permissions import IsOwnerOrAdmin
from rest_framework import generics, permissions
from .models import Listing
from .serializers import ListingSerializer

class PropertyListCreateAPIView(generics.ListCreateAPIView):
    """
    GET: List all approved properties (for public search).
    POST: Create a new property listing (Requires Verified KYC status).
    """
    # Only list properties that are active and approved by admin
    queryset = Property.objects.filter(is_active=True, is_approved=True) 

    def get_serializer_class(self):
        # Use the creation serializer for POST, and the read serializer for GET
        if self.request.method == 'POST':
            return PropertyCreateSerializer
        return PropertyReadSerializer # <-- FIX: Use Read Serializer for GET

    def get_permissions(self):
        if self.request.method == 'POST':
            # Require authentication AND verified KYC status
            return [permissions.IsAuthenticated(), IsVerifiedOrStaff()]
        # Allow anonymous viewing for the list (GET) method
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        # Listings start as unapproved (is_approved=False) and is_active=True by default
        serializer.save(owner=self.request.user, is_approved=False)


class PropertyRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    Handles GET, PUT/PATCH, and DELETE for a single property by UUID.
    """
    queryset = Property.objects.all()
    lookup_field = 'pk' 

    def get_serializer_class(self):
        # ... (Existing logic for serializer class) ...
        if self.request.method in ['PUT', 'PATCH']:
            return PropertyUpdateSerializer
        return PropertyReadSerializer

    def get_permissions(self):
        # ... (Existing logic for permissions) ...
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        
        return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]

    # --- CUSTOM DELETION METHOD (The Fix) ---
    def destroy(self, request, *args, **kwargs):
        """
        Overrides the default destroy method to return a 200 OK with a custom message.
        """
        instance = self.get_object()
        
        # 1. PREPARE response data BEFORE deletion (Safer logic)
        property_title = instance.title
        property_pk = instance.pk # UUID object
        
        # 2. Perform the actual deletion
        self.perform_destroy(instance)
        
        # 3. Return the custom success message with 200 OK status
        return Response(
            # We use str(property_pk) to ensure it's JSON-serializable
            {"message": f"Property '{property_title}' (ID: {property_pk}) was successfully deleted."}, 
            status=status.HTTP_200_OK 
        )
        

class ListingSearchView(APIView):
    def get(self, request):
        # Get coordinates from the user's saved location profile
        user_location = request.user.location # From the UserLocation model we created
        
        if not user_location.latitude or not user_location.longitude:
            return Response({"error": "Location not set"}, status=400)

        # Use the service to get listings within 50km
        listings = ListingLocationService.get_nearby_listings(
            user_lat=user_location.latitude,
            user_lng=user_location.longitude,
            radius_km=50
        )
        
        serializer = ListingSerializer(listings, many=True)
        return Response(serializer.data)
    

class PropertyListCreateAPIView(generics.ListCreateAPIView):
    queryset = Listing.objects.filter(is_active=True)
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class PropertyRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Listing.objects.all()
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        # Allow users to see all active listings, but only owners can edit/delete
        if self.request.method in permissions.SAFE_METHODS:
            return Listing.objects.filter(is_active=True)
        return Listing.objects.filter(owner=self.request.user)