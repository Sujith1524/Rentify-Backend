# apps/users/serializers.py

import re
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.core.validators import validate_email # For email format validation

# Import from enterprise structure
from apps.core.utils import validate_password_complexity 
from apps.users.models import UserKYC
from .tasks import generate_and_cache_otp # This task will use email now

User = get_user_model()


# --- 1. User Registration Serializer ---
class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, min_length=8)
    
    class Meta:
        model = User
        fields = ('email', 'phone', 'password')
        extra_kwargs = {'password': {'write_only': True}}

    def validate_email(self, value):
        # 1. Format Check (Ensures it's a proper email address)
        try:
            validate_email(value)
        except:
            raise serializers.ValidationError("Invalid email format.")
            
        # 2. Uniqueness Check (CRITICAL FIX for IntegrityError)
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "This email address is already registered."
            )
        return value

    def validate_phone(self, value):
        # Uniqueness Check for phone
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError(
                "This phone number is already registered."
            )
        return value

    def validate_password(self, value):
        validate_password_complexity(value) 
        return value

    def create(self, validated_data):
        email = validated_data.pop('email')
        password = validated_data.pop('password')
        phone = validated_data.pop('phone')
        
        user = User.objects.create_user(
            email=email,
            password=password,
            phone=phone,
            **validated_data
        )
        
        user.status = 'pending'
        user.save(update_fields=['status']) 
        
        # CRITICAL FIX: Trigger OTP using email
        generate_and_cache_otp(user.email, purpose='registration')
        
        return user


# --- 2. OTP Verification Serializer (Now uses Email) ---
class OTPVerificationSerializer(serializers.Serializer):
    """
    Validates the email and the OTP code against the Redis cache.
    """
    email = serializers.EmailField(required=True) # Changed from phone to email
    otp_code = serializers.CharField(required=True, min_length=6, max_length=6)

    def validate(self, data):
        email = data.get('email') # Use email as identifier
        otp_code = data.get('otp_code')
        
        try:
            # Check only for users who are currently pending
            user = User.objects.get(email=email, status='pending')
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found or already verified."})

        # CRITICAL FIX: Use email for cache key
        cache_key = f'otp:registration:{email}' 
        stored_otp = cache.get(cache_key)

        if not stored_otp or stored_otp != otp_code:
            raise serializers.ValidationError({"otp_code": "Invalid or expired OTP."})

        data['user'] = user
        return data


# --- 3. Custom JWT Serializer (Login Restriction) ---
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Overrides the default JWT serializer to enforce that the user status is 'active'.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        # Add custom claims to the JWT payload
        token['status'] = user.status
        token['role'] = user.role
        
        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        user = self.user
        
        # Enterprise-level restriction: Only active users can log in
        if user.status != 'active':
            if user.status == 'pending':
                raise serializers.ValidationError(
                    {"detail": "Account is pending OTP verification. Please verify your Email first."}
                )
            # Catches pending_kyc, suspended, etc.
            raise serializers.ValidationError(
                {"detail": f"Account status is '{user.status}'. You cannot log in until your account is active."}
            )

        return data


# --- 4. KYC Submission Serializer ---
class KYCSubmissionSerializer(serializers.Serializer):
    """
    Handles Aadhaar and PAN format validation and global uniqueness checks.
    """
    aadhaar_identifier = serializers.CharField(required=True, max_length=12)
    pan_identifier = serializers.CharField(required=True, max_length=10)

    def validate_aadhaar_identifier(self, value):
        if not re.fullmatch(r'^\d{12}$', value):
            raise serializers.ValidationError("Aadhaar must be exactly 12 digits.")
        
        # Security Check
        if UserKYC.objects.filter(kyc_type='aadhaar', kyc_identifier=value, status__in=['verified', 'submitted']).exists():
            raise serializers.ValidationError("Aadhaar number is already in use by another account.")
        
        return value

    def validate_pan_identifier(self, value):
        value = value.upper()
        if not re.fullmatch(r'^[A-Z]{5}\d{4}[A-Z]{1}$', value):
            raise serializers.ValidationError("PAN must follow the alphanumeric format (e.g., ABCDE1234Z).")

        # Security Check
        if UserKYC.objects.filter(kyc_type='pan', kyc_identifier=value, status__in=['verified', 'submitted']).exists():
            raise serializers.ValidationError("PAN is already in use by another account.")
        
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        
        # Create Aadhaar and PAN records
        UserKYC.objects.create(
            user=user, kyc_type='aadhaar', kyc_identifier=validated_data['aadhaar_identifier'], status='submitted'
        )
        UserKYC.objects.create(
            user=user, kyc_type='pan', kyc_identifier=validated_data['pan_identifier'], status='submitted'
        )
        
        # Update User Status
        if user.status == 'active':
            user.status = 'pending_kyc' 
            user.save(update_fields=['status', 'updated_at'])
            
        return user


# --- 5. User Status Serializer ---
class UserStatusSerializer(serializers.ModelSerializer):
    kyc_status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'phone', 'role', 'status', 'kyc_status', 'created_at')
        read_only_fields = fields

    def get_kyc_status(self, obj):
        # We assume related_name='kyc_records' on the ForeignKey in UserKYC
        last_kyc = obj.kyc_records.order_by('-created_at').first() 
        if not last_kyc:
            return {'status': 'not_submitted', 'submitted_at': None}
        return {
            'status': last_kyc.status,
            'submitted_at': last_kyc.created_at,
            'verified_at': last_kyc.verified_at
        }