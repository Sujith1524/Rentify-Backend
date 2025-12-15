# apps/listings/models.py

from django.db import models
from django.conf import settings
from apps.core.models import BaseModel # Import your BaseModel

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
    
    # --- Timestamps via BaseModel ---
    # created_at, updated_at are inherited from BaseModel

    def __str__(self):
        return f"{self.title} ({self.city}) - {self.transaction_type}"

    class Meta:
        verbose_name_plural = "Properties"
        ordering = ['-created_at']


class PropertyImage(BaseModel):
    """
    Model for storing multiple images associated with a Property.
    Images will be stored on Cloudinary via DEFAULT_FILE_STORAGE.
    """
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(
        upload_to='property_images/%Y/%m/', # Folder structure on Cloudinary
        help_text="Image file for the property."
    )
    is_main = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Image for {self.property.title}"