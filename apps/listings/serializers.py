# apps/listings/serializers.py

from rest_framework import serializers
from django.db import transaction # <-- CRITICAL IMPORT ADDED
from .models import Property, PropertyImage
from rest_framework import serializers
from .models import Listing

# --- 1. Property Image Serializer (Handles URL Strings) ---
class PropertyImageSerializer(serializers.ModelSerializer):
    # CRITICAL FIX: Expect the image_url field instead of 'image'
    class Meta:
        model = PropertyImage
        fields = ['image_url', 'is_main']

# --- 2. Property Read Serializer (For GET requests) ---
class PropertyReadSerializer(serializers.ModelSerializer):
    # Nested serializer to include all image URLs
    images = PropertyImageSerializer(many=True, read_only=True)
    # Include the owner's email for easy display
    owner_email = serializers.ReadOnlyField(source='owner.email')
    
    class Meta:
        model = Property
        fields = [
            'id', 'title', 'description', 'transaction_type', 
            'property_type', 'price', 'address_line_1', 'city', 
            'state', 'zip_code', 'bedrooms', 'bathrooms', 'area_sqft', 
            'images', 'is_approved', 'owner_email', 'created_at'
        ]

# --- 3. Property Create Serializer (Fix fields and nesting) ---
class PropertyCreateSerializer(serializers.ModelSerializer):
    # Accept a list of image objects for nested creation
    images = PropertyImageSerializer(many=True, required=False) 

    class Meta:
        model = Property
        fields = [
            'id', 'title', 'description', 'transaction_type', 
            'property_type', 'price', 'address_line_1', 'city', 
            'state', 'zip_code', 'bedrooms', 'bathrooms', 'area_sqft', 
            'images'
        ]
        read_only_fields = ['id', 'is_approved']

    @transaction.atomic
    def create(self, validated_data):
        images_data = validated_data.pop('images', [])
        
        property_instance = Property.objects.create(**validated_data)
        
        # 2. Create the related PropertyImage objects (using the 'image_url' field)
        for image_data in images_data:
            PropertyImage.objects.create(property=property_instance, **image_data)
            
        return property_instance
    

# --- 4. Property Update Serializer (For PUT/PATCH requests) ---
class PropertyUpdateSerializer(serializers.ModelSerializer):
    # Images are removed from here to simplify PATCH/PUT. 
    # Image updates should be handled via a separate, dedicated endpoint for better control.

    class Meta:
        model = Property
        fields = [
            'id', 'title', 'description', 'transaction_type', 
            'property_type', 'price', 'address_line_1', 'city', 
            'state', 'zip_code', 'bedrooms', 'bathrooms', 'area_sqft', 
            'is_active' # Allow owner to toggle active status
        ]
        read_only_fields = ['id', 'is_approved']
        
    def update(self, instance, validated_data):
        # When updating, we set is_approved back to False if major fields are changed
        # to require re-approval by an admin.
        
        # NOTE: If you want to require re-approval on ANY change, uncomment the line below:
        # instance.is_approved = False 
        
        return super().update(instance, validated_data)
    


class ListingSerializer(serializers.ModelSerializer):
    # This field will capture the 'distance' calculated by our ListingLocationService
    distance = serializers.FloatField(read_only=True)
    owner_email = serializers.EmailField(source='owner.email', read_only=True)

    class Meta:
        model = Listing
        fields = [
            'id', 'owner', 'owner_email', 'title', 'description', 
            'price', 'address', 'latitude', 'longitude', 
            'distance', 'is_active', 'created_at'
        ]
        read_only_fields = ['owner', 'created_at']

    def create(self, validated_data):
        # Automatically assign the logged-in user as the owner
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)