# apps/users/views.py

from rest_framework import views, generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from django.core.cache import cache
from .serializers import KYCDraftSerializer
from .utils import load_kyc_draft, clear_kyc_draft
from .serializers import ( # Cleaned and centralized imports
    UserRegistrationSerializer, 
    OTPVerificationSerializer, 
    CustomTokenObtainPairSerializer, 
    KYCSubmissionSerializer, 
    UserStatusSerializer,
    LoginOTPRequestSerializer,    
    LoginOTPVerificationSerializer,
)

# Import SimpleJWT for token generation later
# Note: The CustomTokenObtainPairView uses the imported TokenObtainPairView

# --- 1. Registration (Pre-DB Save) ---
class RegisterAPIView(generics.CreateAPIView):
    """
    POST /api/v1/auth/register/
    Stores data in cache and sends OTP, does NOT save to database yet.
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = [] 

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # CRITICAL CHANGE: Call save, which stores data in cache and sends OTP
        result = serializer.save() 
        
        return Response({
            "message": f"Pre-registration successful. OTP sent to {result['email']} for verification.",
            "email": result['email'], # Return email for next step
        }, status=status.HTTP_200_OK) # Changed to 200 OK since no object was created in DB
    

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
    """
    POST /api/v1/auth/login/request-otp/
    Authenticates user/password and sends a login OTP via email.
    """
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = LoginOTPRequestSerializer(data=request.data)
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