# apps/listings/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.core.models import BaseModel

# Constants for choices
PROPERTY_TYPE_CHOICES = [
    ('house', 'House'),
    ('apartment', 'Apartment'),
    ('land', 'Land/Plot'),
    ('commercial', 'Commercial'),
]

TRANSACTION_TYPE_CHOICES = [
    ('rent', 'For Rent'),
    ('sale', 'For Sale'),
]

class Property(BaseModel):
    """
    Model representing a single property listing for rent or sale.
    """
    # --- Owner/Status ---
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='property_listings',
        help_text="The user who created and owns this listing."
    )
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False, help_text="Set to True by admin review.")

    # --- Basic Details ---
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPE_CHOICES)

    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # --- Location ---
    address_line_1 = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
    
    # --- Property Specifications ---
    bedrooms = models.PositiveSmallIntegerField(default=1)
    bathrooms = models.PositiveSmallIntegerField(default=1)
    area_sqft = models.PositiveIntegerField(help_text="Total area in square feet.")
    
    def __str__(self):
        return f"{self.title} ({self.city}) - {self.transaction_type}"

    class Meta:
        verbose_name_plural = "Properties"
        ordering = ['-created_at']


class PropertyImage(BaseModel):
    """
    Model for storing multiple images associated with a Property.
    Stores the external Cloudinary URL.
    """
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='images'
    )
    # CRITICAL FIX: Use URLField to store the Cloudinary link string
    image_url = models.URLField(
        max_length=500, 
        help_text="The external Cloudinary URL for the image."
    ) 
    is_main = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Image URL for {self.property.title}"
    

class Listing(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='listings')
    title = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Location fields for Geospatial search
    address = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


    def soft_delete(self):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.is_active = True
        self.deleted_at = None
        self.save()

    def __str__(self):
        return self.title
    

class UserLocation(models.Model):
    # ...
    device_identifier = models.CharField(max_length=255, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True) 