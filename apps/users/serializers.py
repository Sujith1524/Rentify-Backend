# apps/users/serializers.py

import re
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.core.validators import validate_email # For email format validation
from django.db import transaction # New Import for atomic DB operations
from rest_framework_simplejwt.tokens import RefreshToken # New Import for token generation
from apps.core.utils import check_otp, get_tokens_for_user
from django.utils import timezone


# Import from enterprise structure
from apps.core.utils import validate_password_complexity 
from apps.users.models import UserKYC
from .tasks import generate_and_cache_otp # This task will use email now

User = get_user_model()


# --- 1. User Registration Serializer (Now stores data in cache) ---
class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, min_length=8)
    
    class Meta:
        model = User
        fields = ('email', 'phone', 'password')
        extra_kwargs = {'password': {'write_only': True}}

    def validate_email(self, value):
        # 1. Format Check
        try:
            validate_email(value)
        except:
            raise serializers.ValidationError("Invalid email format.")
            
        # 2. CRITICAL CHANGE: Only check against ACTIVE users. 
        # Pending users in cache do not block new registrations.
        if User.objects.filter(email=value, status__in=['active', 'pending_kyc', 'verified']).exists():
            raise serializers.ValidationError(
                "This email address is already registered and active."
            )
        return value

    def validate_phone(self, value):
        # CRITICAL CHANGE: Only check against ACTIVE users.
        if User.objects.filter(phone=value, status__in=['active', 'pending_kyc', 'verified']).exists():
            raise serializers.ValidationError(
                "This phone number is already registered and active."
            )
        return value

    # CRITICAL CHANGE: No 'create' method here. We use 'save' to store in cache.
    def save(self, **kwargs):
        # Store validated data in cache for verification, instead of saving to DB.
        email = self.validated_data['email']
        
        # We cache the entire validated data dictionary for 15 minutes (enough time for OTP + verification)
        cache_key = f'pre_register:{email}'
        cache.set(cache_key, self.validated_data, timeout=900)
        
        # Trigger OTP using email
        otp_code = generate_and_cache_otp(email, purpose='registration')

        # Return the email used for verification
        return {'email': email, 'otp_code': otp_code} # Returning a dict, not a user instance


# --- 2. OTP Verification Serializer (Now creates user and issues tokens) ---
class OTPVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp_code = serializers.CharField(required=True, min_length=6, max_length=6)

    def validate(self, data):
        email = data.get('email')
        otp_code = data.get('otp_code')
        
        # 1. Check Pre-Registration Cache
        pre_register_data = cache.get(f'pre_register:{email}')
        if not pre_register_data:
            raise serializers.ValidationError({"email": "Registration process expired or email not found. Please register again."})

        # 2. Check OTP Cache
        cache_key = f'otp:registration:{email}' 
        stored_otp = cache.get(cache_key)

        if not stored_otp or stored_otp != otp_code:
            raise serializers.ValidationError({"otp_code": "Invalid or expired OTP."})

        # CRITICAL: Store pre_register data for the final save step
        data['pre_register_data'] = pre_register_data
        
        return data

    @transaction.atomic # Ensure DB operations are all-or-nothing
    def save(self, **kwargs):
        data = self.validated_data['pre_register_data']
        email = data['email']
        password = data.pop('password')
        
        # 1. CREATE THE USER IN THE DATABASE (Only upon successful OTP verification)
        user = User.objects.create_user(
            email=email,
            password=password,
            phone=data['phone'],
            status='active' # Immediately set to active since verification is complete
        )
        
        # 2. Cleanup Caches
        cache.delete(f'pre_register:{email}')
        cache.delete(f'otp:registration:{email}')
        
        # 3. CRITICAL NEW LOGIC: Generate Tokens (No need for separate login)
        refresh = RefreshToken.for_user(user)
        
        return {
            'user': user,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
    

# --- 3. Login OTP Request Serializer (NEW for 2FA Login) ---
class LoginOTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        
        user = User.objects.filter(email=email).first()

        if user is None or not user.check_password(password):
            raise serializers.ValidationError({"detail": "Invalid credentials."})
        
        if user.status != 'active' and user.status != 'verified':
             raise serializers.ValidationError({"detail": f"Account status is '{user.status}'. Cannot log in."})
        
        # 1. User validated. Generate and send a new OTP for this session.
        generate_and_cache_otp(user.email, purpose='login')
        
        # 2. Store the user object and success status
        data['user'] = user
        return data


# --- 4. Login OTP Verification Serializer (NEW for 2FA Login) ---
class LoginOTPVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6)

    def validate(self, data):
        email = data.get('email')
        otp_code = data.get('otp_code')

        # 1. Basic user check
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User with this email not found."})

        # 2. Verify OTP against cache
        if not check_otp(email, otp_code, purpose='login'):
            raise serializers.ValidationError({"otp_code": "Invalid or expired OTP code."})

        # 3. Final validation success: attach user to validated_data
        data['user'] = user
        return data

    def get_tokens_for_user(self, user):
        # Assuming this utility function is defined, perhaps imported from .utils
        # and returns {'access': '...', 'refresh': '...'}
        return get_tokens_for_user(user)

    def save(self, **kwargs):
        """
        Generates JWT tokens and cleans up the cache entry.
        """
        user = self.validated_data['user']
        
        # 1. Generate tokens
        tokens = self.get_tokens_for_user(user)
        
        # 2. Cleanup cache
        key = f'otp:login:{user.email}'
        cache.delete(key)
        
        # 3. Update last login time (Optional, but good practice)
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        # 4. CRITICAL FIX: Include the user object in the return dictionary
        # The view (LoginOTPVerifyAPIView) will use this to check the status.
        tokens['user'] = user 
        
        return tokens


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

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        user = request.user
    
        # 1. Create the Aadhaar UserKYC record
        UserKYC.objects.create(
            user=user,
            kyc_type='aadhaar',
            kyc_identifier=validated_data['aadhaar_identifier'],
            status='submitted' # Set KYC record status to submitted
        )
    
        # 2. Create the PAN UserKYC record
        UserKYC.objects.create(
            user=user,
            kyc_type='pan',
            kyc_identifier=validated_data['pan_identifier'],
            status='submitted' # Set KYC record status to submitted
        )
    
        # 3. CRITICAL FIX: Update the main User status to 'pending_kyc' 
        # as per the User Story (awaiting admin review).
        user.status = 'pending_kyc' 
        user.save(update_fields=['status']) 
    
        return user


# --- 5. User Status Serializer ---
class UserStatusSerializer(serializers.ModelSerializer):
    kyc_status = serializers.SerializerMethodField() # <--- Use SerializerMethodField
    
    class Meta:
        model = User
        fields = ('id', 'email', 'phone', 'role', 'status', 'kyc_status', 'created_at')
        read_only_fields = fields

    def get_kyc_status(self, user):
        """
        Fetches the latest KYC submission status and timestamp.
        """
        try:
            # Assumes you have a 'user' related name on UserKYC (default is userkyc_set)
            # Find the most recent, successfully created KYC record
            latest_kyc = UserKYC.objects.filter(user=user).latest('submitted_at') 
            
            # If a record is found, return its data
            return {
                "status": latest_kyc.status, # e.g., 'submitted', 'verified', 'rejected'
                "submitted_at": latest_kyc.submitted_at, # <--- CRITICAL FIX: Timestamp
                "verified_at": latest_kyc.verified_at,   # Include verified_at if applicable
            }
        except UserKYC.DoesNotExist:
            # If no KYC record is found, return the initial state
            return {
                "status": "not_submitted",
                "submitted_at": None,
                "verified_at": None,
            }