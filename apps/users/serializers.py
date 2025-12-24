# apps/users/serializers.py

import re
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.validators import validate_email # For email format validation
from django.db import transaction # New Import for atomic DB operations
from rest_framework_simplejwt.tokens import RefreshToken # New Import for token generation
from .models import Profile, ProfileAuditLog
from apps.core.utils import check_otp, get_tokens_for_user
from django.utils import timezone
from .utils import save_kyc_draft, load_kyc_draft
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from apps.core.notifications import NotificationService
from apps.users.models import User, PendingSensitiveChange
from django.utils import timezone
from .utils import (
    generate_and_cache_otp, 
    record_failed_attempt,     
    is_account_locked,          
    clear_failed_attempts,
    validate_otp, 
    clear_otp_from_cache,
)


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
    

class LoginOTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        
        user = User.objects.filter(email=email).first()

        # 1. Lockout Check
        if is_account_locked(email):
            raise serializers.ValidationError({"detail": "Too many failed login attempts. Account temporarily locked."})
        
        # 2. Authentication Check
        if user is None or not user.check_password(password):
            record_failed_attempt(email) 
            if is_account_locked(email):
                raise serializers.ValidationError({"detail": "Too many failed attempts. Account temporarily locked."})
            raise serializers.ValidationError({"detail": "Invalid credentials."})
        
        # 3. Successful Auth - Clear attempts
        clear_failed_attempts(email) 

        # 4. Status Check
        ALLOWED_LOGIN_STATUSES = ['active', 'pending_kyc', 'rejected', 'verified']
        if user.status not in ALLOWED_LOGIN_STATUSES:
            raise serializers.ValidationError({"detail": f"Account status is '{user.status}'. Restricted."})
            
        # 5. Generate OTP
        otp_code = generate_and_cache_otp(user.email, purpose='login')

        # 6. TRIGGER NOTIFICATION HERE (Safe, no KeyError)
        otp_code = generate_and_cache_otp(user.email, purpose='login')
        NotificationService.send_html_email(
            user_email=user.email,
            subject="Your Rentify Secure Login Code",
            template_name="login_otp",
            context={
                'otp': otp_code,
                'timestamp': timezone.now().strftime('%d %b %Y, %I:%M %p')
            }
        )
        
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


# --- 4. KYC Submission Serializer ---
class KYCSubmissionSerializer(serializers.Serializer):
    """
    Handles Aadhaar and PAN format validation and global uniqueness checks.
    Enforces EITHER kyc_identifier OR document_file submission for each type.
    """
    # Aadhaar fields
    aadhaar_identifier = serializers.CharField(max_length=100, required=False, allow_blank=True)
    aadhaar_document = serializers.FileField(required=False)

    # PAN fields
    pan_identifier = serializers.CharField(max_length=100, required=False, allow_blank=True)
    pan_document = serializers.FileField(required=False)
    
    # ----------------------------------------------------
    # Individual Field Validation (Runs only if field is provided)
    # ----------------------------------------------------

    def validate_aadhaar_identifier(self, value):
        # Format Check
        if not re.fullmatch(r'^\d{12}$', value):
            raise serializers.ValidationError("Aadhaar must be exactly 12 digits.")
        
        # Uniqueness Check
        if UserKYC.objects.filter(kyc_type='aadhaar', kyc_identifier=value, status__in=['verified', 'submitted']).exists():
            # User Story: Notify the user without revealing the existing account identity
            raise serializers.ValidationError("Aadhaar number is already in use by another account.")
        
        return value

    def validate_pan_identifier(self, value):
        value = value.upper()
        # Format Check (e.g., AAAAA9999A)
        if not re.fullmatch(r'^[A-Z]{5}\d{4}[A-Z]{1}$', value):
            raise serializers.ValidationError("PAN must follow the alphanumeric format (e.g., ABCDE1234Z).")

        # Uniqueness Check
        if UserKYC.objects.filter(kyc_type='pan', kyc_identifier=value, status__in=['verified', 'submitted']).exists():
            # User Story: Notify the user without revealing the existing account identity
            raise serializers.ValidationError("PAN is already in use by another account.")
        
        return value

    # ----------------------------------------------------
    # Global Validation (CRITICAL: Enforces EITHER/OR logic)
    # ----------------------------------------------------
    def validate(self, data):
        
        # --- Aadhaar EITHER/OR Check ---
        aadhaar_id = data.get('aadhaar_identifier')
        aadhaar_doc = data.get('aadhaar_document')
        
        # CRITICAL: Check if NEITHER the identifier NOR the document is provided
        if not aadhaar_id and not aadhaar_doc:
            raise serializers.ValidationError({
                'aadhaar': "Either the Aadhaar Identifier or the Aadhaar Document must be submitted."
            })
            
        # --- PAN EITHER/OR Check ---
        pan_id = data.get('pan_identifier')
        pan_doc = data.get('pan_document')

        # CRITICAL: Check if NEITHER the identifier NOR the document is provided
        if not pan_id and not pan_doc:
            raise serializers.ValidationError({
                'pan': "Either the PAN Identifier or the PAN Document must be submitted."
            })

        return data

    # ----------------------------------------------------
    # Create Method (Handles saving both fields)
    # ----------------------------------------------------
    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
    
        # 1. Create the Aadhaar UserKYC record
        UserKYC.objects.create(
            user=user,
            kyc_type='aadhaar',
            # Stores ID (if provided) or None
            kyc_identifier=validated_data.get('aadhaar_identifier'), 
            # Stores File (Cloudinary URL) (if provided) or None
            document_file=validated_data.get('aadhaar_document'), 
            status='submitted'
        )
    
        # 2. Create the PAN UserKYC record
        UserKYC.objects.create(
            user=user,
            kyc_type='pan',
            # Stores ID (if provided) or None
            kyc_identifier=validated_data.get('pan_identifier'),
            # Stores File (Cloudinary URL) (if provided) or None
            document_file=validated_data.get('pan_document'),
            status='submitted'
        )
    
        # 3. Update the main User status to 'pending_kyc' 
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
        

class KYCDraftSerializer(serializers.Serializer):
    """
    Serializer for saving/loading partial KYC form data (drafts).
    """
    aadhaar_identifier = serializers.CharField(max_length=100, required=False, allow_blank=True)
    aadhaar_document = serializers.CharField(required=False, allow_blank=True) # Will store file URL/name placeholder
    pan_identifier = serializers.CharField(max_length=100, required=False, allow_blank=True)
    pan_document = serializers.CharField(required=False, allow_blank=True) # Will store file URL/name placeholder

    def save_draft(self, user):
        data = self.validated_data
        # Note: We skip complex file handling here; we assume the frontend sends
        # the Cloudinary public ID or URL after the file is uploaded.
        save_kyc_draft(user.id, data)
        return data

    def load_draft(self, user):
        data = load_kyc_draft(user.id)
        # Note: If data is loaded, it bypasses field validation in the view
        return data
    
    
class KYCReviewSerializer(serializers.Serializer):
    """
    Handles the action of an admin reviewing a user's KYC submission.
    """
    # CRITICAL FIX: Change to UUIDField to accept the UUID string
    user_id = serializers.UUIDField(required=True) 
    action = serializers.ChoiceField(choices=['approve', 'reject'], required=True)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True) 

    def validate_user_id(self, value):
        # DRF's UUIDField automatically validates the format of the string.
        # Here, 'value' is already converted to a Python UUID object.
        
        # Ensure the user exists using the UUID object
        try:
            # We must use pk=value because the user model's primary key is the UUID
            user = User.objects.get(pk=value) 
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")
        
        # Ensure the user is in a reviewable state
        if user.status not in ['pending_kyc', 'rejected']:
            raise serializers.ValidationError(f"User is not in a reviewable state. Current status: {user.status}")
            
        return value
    

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        # 1. Check for user existence
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            # DANGER: THIS EXPOSES USER EXISTENCE (Violation of OWASP)
            raise serializers.ValidationError("Account not found with this email address.") 
        
        # 2. Block suspended/disabled accounts
        if user.status == 'suspended' or user.status == 'disabled':
             raise serializers.ValidationError("Account is suspended or deactivated. Cannot initiate password reset.")

        self.user = user
        return value
    

class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp_code = serializers.CharField(required=True, max_length=6)
    new_password = serializers.CharField(required=True, write_only=True, min_length=8)

    def validate(self, data):
        email = data['email']
        new_password = data['new_password']
        
        # 1. Check user existence
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "Invalid email."})
        
        # 2. Validate the OTP
        # CRITICAL FIX: Use the OTP validation utility
        if not validate_otp(email, data['otp_code'], purpose='reset'):
            # Rule 2: Deny expired/invalid OTP
            raise serializers.ValidationError({"otp_code": "Invalid or expired OTP. Please request a new code."})
            
        # 3. Check if new password is the same as the old password
        if user.check_password(new_password):
            # NEW RULE: The user cannot use the existing password
            raise serializers.ValidationError({"new_password": "This password is your current one. Please choose a new password."})

        self.user = user
        return data

    @transaction.atomic
    def save(self, **kwargs):
        user = self.user
        new_password = self.validated_data['new_password']
        
        # 1. Set the new password and update the invalidation timestamp
        user.set_password(new_password)
        user.password_updated_at = timezone.now()
        user.save(update_fields=['password', 'password_updated_at']) 
        
        # 2. Clear the used OTP from cache (Rule 2)
        clear_otp_from_cache(user.email, purpose='reset')
        
        return user
    

class LogoutSerializer(serializers.Serializer):
    """
    Serializer to accept and validate the Refresh Token for blacklisting.
    """
    refresh = serializers.CharField(required=True)

    def validate(self, attrs):
        self.token = attrs['refresh']
        return attrs

    def save(self, **kwargs):
        """
        Attempts to blacklist the token.
        """
        try:
            # 1. Instantiate the RefreshToken object with the token string
            token = RefreshToken(self.token)
            
            # 2. Blacklist the token (this is the core logout action)
            token.blacklist()
            
        except TokenError:
            # This handles cases where the token is already blacklisted, expired, 
            # or malformed. We let it fail silently to avoid leaking info.
            # In a real-world scenario, you might log this error.
            pass
        except Exception as e:
            # General error handling
            raise serializers.ValidationError({"detail": "Error during token invalidation."})
        


class ProfileSerializer(serializers.ModelSerializer):
    # Flatten fields from your Custom User model
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    
    # Use 'phone' to match your User model definition
    email = serializers.EmailField(source='user.email', read_only=True) 
    phone = serializers.CharField(source='user.phone', read_only=True) 
    
    # Requirement 1: KYC status from User.status field
    kyc_status = serializers.CharField(source='user.status', read_only=True)

    class Meta:
        model = Profile
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'profile_photo', 
            'alternate_mobile', 'bio', 'pref_email_notifications', 
            'pref_sms_notifications', 'pref_push_notifications', 'kyc_status'
        ]

    def validate_first_name(self, value):
        # Requirement 2: Name character-formatting rules
        if not value.replace(' ', '').isalpha():
            raise serializers.ValidationError("Name must contain only alphabetical characters.")
        return value

    def validate_profile_photo(self, value):
        # Requirement 3: Photo data integrity and format
        if value and "cloudinary.com" not in value:
            raise serializers.ValidationError("Only Cloudinary hosted images are accepted.")
        return value

    def validate(self, data):
        """
        Requirement 1: Restricted fields (Name) must not be editable after KYC verification.
        """
        user = self.instance.user
        
        # Check against your User model's 'status' field
        if user.status == 'verified':
            user_data = data.get('user', {})
            restricted_fields = ['first_name', 'last_name'] 
            
            for field in restricted_fields:
                if field in user_data:
                    raise serializers.ValidationError({
                        field: f"Cannot update {field} because your account is already KYC verified."
                    })
        return data

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        user = instance.user

        # Requirement 5: Audit Logging for Profile fields
        for attr, value in validated_data.items():
            old_val = getattr(instance, attr)
            if old_val != value:
                ProfileAuditLog.objects.create(
                    user=user,
                    field_name=attr,
                    old_value=str(old_val),
                    new_value=str(value),
                    action_by=user
                )
                setattr(instance, attr, value)

        # Update core User fields (first_name, last_name)
        if user_data:
            for attr, value in user_data.items():
                old_val = getattr(user, attr)
                if old_val != value:
                    # Requirement 5: Audit Logging for User identity fields
                    ProfileAuditLog.objects.create(
                        user=user,
                        field_name=attr,
                        old_value=str(old_val),
                        new_value=str(value),
                        action_by=user
                    )
                    setattr(user, attr, value)
            user.save()

        instance.save()
        return instance
    

    
class SensitiveChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField(required=False)
    new_mobile = serializers.CharField(required=False)

    def validate(self, data):
        new_email = data.get('new_email')
        new_mobile = data.get('new_mobile')
        
        # Get the user safely from context
        request = self.context.get('request')
        user_id = request.user.id if request and request.user else None

        from apps.users.models import User

        if new_email:
            # Check if email exists and belongs to SOMEONE ELSE
            query = User.objects.filter(email=new_email)
            if user_id:
                query = query.exclude(id=user_id)
            if query.exists():
                raise serializers.ValidationError({"new_email": "This email is already in use."})

        if new_mobile:
            # Check if phone exists and belongs to SOMEONE ELSE
            query = User.objects.filter(phone=new_mobile)
            if user_id:
                query = query.exclude(id=user_id)
            if query.exists():
                raise serializers.ValidationError({"new_mobile": "This phone number is already in use."})

        return data
    


class ResendOTPSerializer(serializers.Serializer):
    PURPOSE_CHOICES = (
        ('registration', 'Registration'),
        ('login', 'Login'),
        ('reset', 'Password Reset'),
        ('change', 'Sensitive Change'),
    )
    email = serializers.EmailField(required=False)
    purpose = serializers.ChoiceField(choices=PURPOSE_CHOICES)

    def validate(self, data):
        purpose = data.get('purpose')
        email = data.get('email')
        
        # 1. Logic for Registration (Checks Cache)
        if purpose == 'registration':
            if not email:
                raise serializers.ValidationError({"email": "Email is required for registration resend."})
            if not cache.get(f'pre_register:{email}'):
                raise serializers.ValidationError({"detail": "Registration session expired. Please register again."})

        # 2. Logic for Login/Reset (Checks User Table)
        elif purpose in ['login', 'reset']:
            if not email:
                raise serializers.ValidationError({"email": "Email is required."})
            if not User.objects.filter(email=email).exists():
                raise serializers.ValidationError({"detail": "User not found."})

        # 3. Logic for Sensitive Change (Checks Auth and Pending Record)
        elif purpose == 'change':
            request = self.context.get('request')
            if not request.user.is_authenticated:
                raise serializers.ValidationError({"detail": "Authentication required."})
            if not PendingSensitiveChange.objects.filter(user=request.user).exists():
                raise serializers.ValidationError({"detail": "No pending change request found."})

        return data