# apps/users/models.py

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from apps.core.models import BaseModel


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
        ('pending_kyc', 'Waiting for KYC Review'),
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

class UserKYC(BaseModel):
    # FIXED related_name to kyc_records to match serializer logic
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='kyc_records') 
    kyc_type = models.CharField(max_length=20) 
    kyc_identifier = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default='submitted')
    verified_at = models.DateTimeField(null=True, blank=True)