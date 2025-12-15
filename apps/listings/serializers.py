# apps/listings/serializers.py

from rest_framework import serializers
from .models import Property, PropertyImage

# Handles the file upload for one image
class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ['image', 'is_main']

# Handles the main property details
class PropertyCreateSerializer(serializers.ModelSerializer):
    # This field expects a list of dictionaries corresponding to the images
    images = PropertyImageSerializer(many=True, required=False) 

    class Meta:
        model = Property
        # Fields that the user can submit
        fields = [
            'id', 'title', 'description', 'transaction_type', 
            'property_type', 'price', 'address_line_1', 'city', 
            'state', 'zip_code', 'bedrooms', 'bathrooms', 'area_sqft', 
            'images'
        ]
        read_only_fields = ['id', 'is_approved']

    def create(self, validated_data):
        # Extract images data if provided, otherwise default to an empty list
        images_data = validated_data.pop('images', [])
        
        # 1. Create the main Property object
        # The user is attached from the view (owner=self.context['request'].user)
        property_instance = Property.objects.create(**validated_data)
        
        # 2. Create the related PropertyImage objects
        for image_data in images_data:
            PropertyImage.objects.create(property=property_instance, **image_data)
            
        return property_instance