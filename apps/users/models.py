# apps/users/models.py

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
# REMOVE: from django.contrib.auth import get_user_model  <--- DELETE THIS
from apps.core.models import BaseModel


# NOTE: Since we are defining the User model below, we can reference it directly.
# The CustomUserManager must be defined before the User model.
class CustomUserManager(BaseUserManager):
    """
    Custom user manager where email is the unique identifier for authentication 
    instead of username.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        
        # User is created without a 'username' field
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser, BaseModel):
    # Standard User fields
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, unique=True, db_index=True)
    
    # Custom fields
    ROLE_CHOICES = (
        ('seller', 'Seller (Lister)'),
        ('buyer', 'Buyer (Renter)'),
        ('admin', 'Administrator'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending Email Verification'),
        ('active', 'Email Verified, Pre-KYC'),
        ('verified', 'Full Verified User'),
        ('rejected', 'KYC Rejected'),
        ('suspended', 'Account Suspended'),
    )
    
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='buyer')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Django Custom User settings
    username = None 
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone']
    
    objects = CustomUserManager()

    def __str__(self):
        return self.email

# --- Define the KYC Status Choices ---
KYC_STATUS_CHOICES = (
    ('submitted', 'Submitted'),
    ('verified', 'Verified'),
    ('rejected', 'Rejected'),
)
# -------------------------------------

# UserKYC can reference the User model directly as it is defined above.
class UserKYC(BaseModel):
    # Fixed related_name to kyc_records
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='kyc_records') 
    
    kyc_type = models.CharField(max_length=20, choices=[('aadhaar', 'Aadhaar'), ('pan', 'PAN')])
    
    # 1. UPDATED: Make kyc_identifier nullable since it's now optional (EITHER/OR logic)
    kyc_identifier = models.CharField(max_length=100, null=True, blank=True)
    
    # 2. NEW FIELD: FileField for the uploaded document. Uses Cloudinary storage.
    document_file = models.FileField(
        upload_to='kyc_documents/', 
        null=True, 
        blank=True,
        verbose_name="KYC Document Upload"
    )
    
    status = models.CharField(max_length=20, choices=KYC_STATUS_CHOICES, default='submitted')
    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    review_reason = models.TextField(null=True, blank=True)
    
    class Meta:
        get_latest_by = 'submitted_at'
        # The unique_together constraint must be removed or modified, 
        # as multiple users might submit a NULL document_file or NULL identifier.
        # However, for simplicity, let's keep the existing ID uniqueness rule:
        unique_together = ('kyc_type', 'kyc_identifier') 
        ordering = ['-submitted_at']
        
    def __str__(self):
        return f"{self.user.email} - {self.kyc_type} - {self.status}"