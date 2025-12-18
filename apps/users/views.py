# apps/users/views.py

import random
import threading
from django.conf import settings
from django.core.mail import send_mail
from rest_framework.views import APIView
from rest_framework import views, generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.cache import cache
from .utils import load_kyc_draft, clear_kyc_draft
from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAdminUser
from apps.users.permissions import IsVerifiedOrStaff
from rest_framework import permissions
from .models import Profile, PendingSensitiveChange
from .serializers import ProfileSerializer
from django.utils import timezone
from .models import UserKYC, ProfileAuditLog
from django.db import transaction 
from django.db import IntegrityError
from apps.core.notifications import NotificationService
from django.utils import timezone
from .serializers import ( 
    UserRegistrationSerializer, 
    OTPVerificationSerializer, 
    KYCSubmissionSerializer, 
    UserStatusSerializer,
    LoginOTPRequestSerializer,    
    LoginOTPVerificationSerializer,
    KYCDraftSerializer,
    KYCReviewSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    LogoutSerializer,
    SensitiveChangeRequestSerializer,
)

User = get_user_model()

# Import SimpleJWT for token generation later
# Note: The CustomTokenObtainPairView uses the imported TokenObtainPairView

# --- 1. Registration (Pre-DB Save) ---
class RegisterAPIView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [] 

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # result contains {'email': email, 'otp_code': otp_code}
        result = serializer.save() 
        
        # FIX: Define the email variable from the result dictionary
        user_email = result.get('email')
        otp_code = result.get('otp_code')

        # Trigger the professional HTML email
        NotificationService.send_html_email(
            user_email=user_email, 
            subject="Welcome to Rentify - Verify Your Account", 
            template_name="registration_otp", 
            context={"otp": otp_code}
        )
        
        return Response({
            "message": f"Pre-registration successful. OTP sent to {user_email} for verification.",
            "email": user_email,
        }, status=status.HTTP_200_OK)
    

# --- 2. OTP Verification (Now performs DB Save and issues tokens) ---
class OTPVerifyAPIView(views.APIView):
    """
    POST /api/v1/auth/verify-otp/
    Verifies OTP, CREATES the user in DB, and issues JWT tokens.
    """
    permission_classes = []
    
    def post(self, request, *args, **kwargs):
        serializer = OTPVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # CRITICAL CHANGE: Call save, which creates user and issues tokens
        result = serializer.save() 
        user = result['user']
        
        return Response({
            "message": "Verification successful. Account created and active. Use the token to proceed with KYC.",
            "user_id": str(user.id),
            "access": result['access'],
            "refresh": result['refresh'],
        }, status=status.HTTP_200_OK)
    


# --- 3. Login OTP Request (NEW) ---
class LoginOTPRequestAPIView(views.APIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = LoginOTPRequestSerializer(data=request.data)
        # The notification now triggers inside .is_valid() -> .validate()
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        
        return Response({
            "message": f"Authentication successful. OTP sent to {user.email} for 2FA.",
            "email": user.email,
        }, status=status.HTTP_200_OK)


# --- 4. Login OTP Verification (NEW) ---
class LoginOTPVerifyAPIView(views.APIView):
    """
    POST /api/v1/auth/login/verify-otp/
    Verifies OTP and issues JWT tokens for login.
    Checks user status to advise the frontend on the next mandatory step (KYC).
    """
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = LoginOTPVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # 1. Call save() to verify OTP, delete cache, and issue tokens.
        #    NOTE: The serializer's save() method must return a dictionary 
        #    containing {'access': ..., 'refresh': ..., 'user': user_object}
        tokens_and_user = serializer.save() 
        
        # 2. CRITICAL FIX: Extract user object and tokens
        user = tokens_and_user.pop('user') # Get user object
        tokens = tokens_and_user           # Tokens are the remaining items

        # 3. Determine the required next step based on the strict User Story status
        next_step = 'listings_access' # Default to full access

        if user.status == 'active':
            # User verified email but hasn't submitted KYC yet
            next_step = 'kyc_required' 
        elif user.status == 'pending_kyc':
            # User submitted KYC but is waiting for admin review (User Story status)
            next_step = 'pending_review' 
        elif user.status == 'rejected':
            # User's KYC was rejected
            next_step = 'kyc_resubmit_required' 
        
        # 4. Return the final response
        return Response({
            "message": f"Login 2FA successful. Your current status is '{user.status}'.",
            "access": tokens['access'],
            "refresh": tokens['refresh'],
            "user_status": user.status, 
            "next_step": next_step      # Frontend uses this field to redirect the user
        }, status=status.HTTP_200_OK)



# CRITICAL FIX: Simplify the KYCSubmissionAPIView
class KYCSubmissionAPIView(views.APIView): # Change from generics.CreateAPIView to views.APIView
    """
    POST /api/v1/auth/kyc/submit/
    Submits Aadhaar and PAN for verification. Requires JWT authentication.
    """
    serializer_class = KYCSubmissionSerializer # Keep this to retrieve the serializer
    permission_classes = [IsAuthenticated] 

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        # This calls the create method which saves data to DB and sets status to 'pending_kyc'
        serializer.save()
        
        # CRITICAL FIX: Clear the draft from cache upon successful final submission
        clear_kyc_draft(request.user.id)
        
        # ... (rest of the response)
        return Response({
            "message": "KYC details submitted successfully. Status is now 'pending_kyc' and awaiting verification.",
            "status": request.user.status 
        }, status=status.HTTP_201_CREATED)
    

class UserStatusAPIView(generics.RetrieveAPIView):
    """
    GET /api/v1/auth/status/
    Returns the user's current status (active, pending_kyc, suspended) and latest KYC details.
    """
    serializer_class = UserStatusSerializer
    permission_classes = [IsAuthenticated] 

    def get_object(self):
        return self.request.user
    


class KYCDraftSaveAPIView(generics.GenericAPIView):
    """
    POST /api/v1/auth/kyc/save-draft/
    Saves partially entered KYC data to the cache for recovery.
    """
    serializer_class = KYCDraftSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=False) # Important: Allow invalid data for drafts

        serializer.save_draft(request.user)
        
        return Response({
            "message": "KYC draft saved successfully to cache.",
        }, status=status.HTTP_200_OK)


class KYCDraftLoadAPIView(generics.RetrieveAPIView):
    """
    GET /api/v1/auth/kyc/load-draft/
    Retrieves the last saved KYC draft from the cache.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        draft_data = load_kyc_draft(request.user.id)
        
        if draft_data:
            return Response(draft_data, status=status.HTTP_200_OK)
        
        return Response({
            "message": "No KYC draft found.",
            "data": {}
        }, status=status.HTTP_404_NOT_FOUND)
    

# Kyc Admin Approval Endpoint
class KYCReviewAPIView(generics.GenericAPIView):
    """
    POST /api/v1/auth/admin/kyc-review/
    Allows administrative staff to approve or reject a pending KYC submission.
    """
    serializer_class = KYCReviewSerializer
    permission_classes = [IsAuthenticated, IsAdminUser] # Only staff can access

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        user_uuid = data['user_id'] # Now this is a UUID object, not an integer
        action = data['action']
        reason = data.get('reason', '')
        
        # Retrieve the user using the UUID (pk=user_uuid)
        user = User.objects.get(pk=user_uuid) 
        now = timezone.now()
        
        if action == 'approve':
            # 1. Update the main User status
            user.status = 'verified'
            user.save(update_fields=['status'])
            
            # 2. Update the related KYC records (Aadhaar and PAN)
            UserKYC.objects.filter(user=user, status__in=['submitted', 'rejected']).update(
                status='verified',
                verified_at=now
            )
            
            # TODO: OPTIONAL: Send a "KYC Approved" email notification to the user
            message = f"User {user.email} KYC Approved. Status is now 'verified'."

        elif action == 'reject':
            # 1. Update the main User status
            user.status = 'rejected'
            user.save(update_fields=['status'])
            
            # 2. Update the related KYC records
            UserKYC.objects.filter(user=user, status__in=['submitted', 'rejected']).update(
                status='rejected',
                verified_at=now, # Using verified_at to mark review time
                review_reason=reason # Assuming you added a review_reason field to UserKYC
            )
            
            # TODO: OPTIONAL: Send a "KYC Rejected" email with the reason to the user
            message = f"User {user.email} KYC Rejected. Status is now 'rejected'. Reason: {reason}"

        return Response({
            "message": message,
            "user_status": user.status,
            "kyc_updated": True
        }, status=status.HTTP_200_OK)
    

class PasswordResetRequestAPIView(generics.GenericAPIView):
    """
    POST /api/v1/auth/password/reset/request/
    Initiates password reset by sending a link to the user's email.
    """
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        # If validate_email fails (user not found), the next line throws 
        # a 400 Bad Request error with the message "Account not found..."
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True) 

        # If validation succeeds (user found), we proceed
        serializer.save(request=request)

        # Success message when user is found and OTP is sent
        return Response({
            "message": "An OTP for password reset has been sent to your email."
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmAPIView(generics.GenericAPIView):
    """
    POST /api/v1/auth/password/reset/confirm/
    Sets a new password using the UID and token from the email link.
    """
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Save updates the password and handles session invalidation
        serializer.save()

        return Response({
            "message": "Password has been reset successfully. You can now log in with your new password."
        }, status=status.HTTP_200_OK)
    

class LogoutAPIView(generics.GenericAPIView):
    """
    POST /api/v1/auth/logout/
    Blacklists the provided Refresh Token, effectively logging the user out 
    from all devices (or specific device if only Access Token is terminated).
    Blacklisting the Refresh Token invalidates all future Access Tokens.
    """
    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated] # User must be logged in to log out

    def post(self, request, *args, **kwargs):
        # We read the Refresh Token from the request body
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # The save method handles the blacklisting logic
        serializer.save()
        
        # Rule 3: Return a success message indicating session termination
        return Response({"message": "Successfully logged out. Your session has been terminated."}, 
                        status=status.HTTP_200_OK)
    

class UserProfileAPIView(generics.RetrieveUpdateAPIView):
    """
    GET: View own profile details.
    PATCH: Update personal information and preferences.
    """
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Requirement 4: Atomic and specific to the authenticated user
        profile, created = Profile.objects.get_or_create(user=self.request.user)
        return profile
    


def get_client_ip(request):
    """Utility to get user IP for audit logs."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

class RequestSensitiveChangeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # FIX: Pass the request context here
        serializer = SensitiveChangeRequestSerializer(
            data=request.data, 
            context={'request': request} 
        )
        serializer.is_valid(raise_exception=True)
        
        otp = f"{random.randint(100000, 999999)}"
        
        PendingSensitiveChange.objects.update_or_create(
            user=request.user,
            defaults={
                'new_email': serializer.validated_data.get('new_email'),
                'new_mobile': serializer.validated_data.get('new_mobile'),
                'otp': otp,
                'created_at': timezone.now()
            }
        )
        
        # UPDATED: Using professional HTML template for the Request phase
        # This replaces the old threading send_mail block
        NotificationService.send_html_email(
            user_email=request.user.email,
            subject="Security Verification: Account Update",
            template_name="login_otp",  # We reuse the login_otp template as it highlights the code perfectly
            context={
                'otp': otp,
                'timestamp': timezone.now().strftime('%d %b %Y, %I:%M %p')
            }
        )
        
        return Response({"message": "OTP sent to your registered email address."}, status=status.HTTP_200_OK)

class VerifySensitiveChangeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        otp_input = request.data.get('otp')
        try:
            pending = PendingSensitiveChange.objects.get(user=request.user)
        except PendingSensitiveChange.DoesNotExist:
            return Response({"error": "No pending update found."}, status=status.HTTP_400_BAD_REQUEST)

        if not pending.is_valid() or pending.otp != otp_input:
            return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        device_ip = get_client_ip(request) 
        changed_fields = []
        summary_fields = [] 

        if pending.new_email:
            ProfileAuditLog.objects.create(
                user=user, field_name="email", 
                old_value=user.email, new_value=pending.new_email,
                device_identifier=device_ip, action_by=user
            )
            user.email = pending.new_email
            changed_fields.append('email')
            summary_fields.append("Email Address")
        
        if pending.new_mobile:
            ProfileAuditLog.objects.create(
                user=user, field_name="phone", 
                old_value=str(user.phone), new_value=pending.new_mobile,
                device_identifier=device_ip, action_by=user
            )
            user.phone = pending.new_mobile
            changed_fields.append('phone')
            summary_fields.append("Phone Number")

        # 4. Atomic Save with Integrity Protection
        if changed_fields:
            try:
                user.save(update_fields=changed_fields)
                
                # Trigger the email ONLY after a successful database save
                NotificationService.send_html_email(
                    user_email=user.email,
                    subject="Security Alert: Profile Updated",
                    template_name="profile_updated",
                    context={
                        "name": user.first_name or "User",
                        "updates": summary_fields,
                        "timestamp": timezone.now().strftime('%d %b %Y, %I:%M %p')
                    },
                    user=user 
                )
                
            except IntegrityError:
                return Response(
                    {"error": "The email or phone number is already registered to another account."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 5. Cleanup
        pending.delete()
        
        return Response({
            "message": "Profile contact information updated successfully."
        }, status=status.HTTP_200_OK)