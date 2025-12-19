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
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Owners can see their deleted items to restore them
        # Others only see active items
        user = self.request.user
        if self.request.method in permissions.SAFE_METHODS:
            return Listing.objects.filter(is_active=True)
        return Listing.objects.filter(owner=user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete() # Logic from model
        
        return Response({
            "message": f"Listing '{instance.title}' has been soft-deleted (deactivated).",
            "id": instance.id,
            "is_active": instance.is_active
        }, status=status.HTTP_200_OK)

#  Soft Deleted Property Restore
class PropertyRestoreAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # We look for the listing specifically among the owner's inactive ones
        try:
            listing = Listing.objects.get(pk=pk, owner=request.user, is_active=False)
        except Listing.DoesNotExist:
            return Response({"error": "Listing not found or already active."}, status=404)
        
        listing.restore()
        return Response({
            "message": f"Listing '{listing.title}' has been successfully restored.",
            "is_active": listing.is_active
        }, status=status.HTTP_200_OK)



class NearbyListingAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # 1. Get the user's saved location
        try:
            user_location = request.user.location
        except Exception:
            return Response({"error": "Please set your location first."}, status=400)

        # 2. Get radius from query params (default to 50km)
        radius = request.query_params.get('radius', 50)

        # 3. Call the Service
        listings = ListingLocationService.get_nearby_listings(
            user_lat=user_location.latitude,
            user_lng=user_location.longitude,
            radius_km=radius
        )

        serializer = ListingSerializer(listings, many=True)
        return Response({
            "user_location": user_location.address,
            "search_radius": f"{radius}km",
            "results": serializer.data
        })