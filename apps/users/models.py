# apps/users/models.py

import datetime
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.core.models import BaseModel
from django.contrib.auth.models import AbstractUser, BaseUserManager


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
    password_updated_at = models.DateTimeField(
        default=timezone.now, 
        help_text="Time of the last password update for JWT validation."
    )

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
    

class Profile(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='profile'
    )
    
    # --- Profile Details ---
    profile_photo = models.URLField(max_length=500, blank=True, null=True)
    alternate_mobile = models.CharField(max_length=15, blank=True, null=True)
    bio = models.TextField(max_length=500, blank=True)
    
    # --- Communication Preferences ---
    pref_email_notifications = models.BooleanField(default=True)
    pref_sms_notifications = models.BooleanField(default=True)
    pref_push_notifications = models.BooleanField(default=True)

    def __str__(self):
        return f"Profile for {self.user.email}"

class ProfileAuditLog(BaseModel):
    """
    Requirement 5: Audit Logging and Recovery.
    Tracks every change made to a user's profile.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='audit_logs'
    )
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    device_identifier = models.CharField(max_length=255, blank=True, null=True)
    action_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='actions_performed'
    )

    class Meta:
        ordering = ['-created_at']


class PendingSensitiveChange(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='pending_change'
    )
    new_email = models.EmailField(null=True, blank=True)
    new_mobile = models.CharField(max_length=15, null=True, blank=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(default=timezone.now)

    def is_valid(self):
        now = timezone.now()
        # 900 seconds = 15 minutes
        return (now - self.created_at).total_seconds() < 900
    

class UserLocation(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='location')
    
    # Coordinates
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    
    # Human readable info
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    
    # Metadata for the Audit/Logging requirement
    method = models.CharField(max_length=20, choices=[('gps', 'GPS'), ('manual', 'Manual')])
    device_identifier = models.CharField(max_length=255, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.city or 'Unknown Location'}"
    

class PasswordResetOTP(models.Model):
    email = models.EmailField(unique=True)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now=True) # auto_now handles timing automatically

    class Meta:
        db_table = 'users_password_reset_otp' # Explicitly naming the table