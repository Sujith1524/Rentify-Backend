# apps/users/views.py

from rest_framework import views, generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from django.core.cache import cache
from .serializers import ( # Cleaned and centralized imports
    UserRegistrationSerializer, 
    OTPVerificationSerializer, 
    CustomTokenObtainPairSerializer, 
    KYCSubmissionSerializer, 
    UserStatusSerializer
)

# Import SimpleJWT for token generation later
# Note: The CustomTokenObtainPairView uses the imported TokenObtainPairView

class RegisterAPIView(generics.CreateAPIView):
    """
    POST /api/v1/auth/register/
    Registers a new user and sends an initial OTP for verification (via Email).
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = [] 

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        return Response({
            "message": "User registered successfully. OTP sent to your email address for verification.",
            "user_id": str(user.id),
        }, status=status.HTTP_201_CREATED)
    

class OTPVerifyAPIView(views.APIView):
    """
    POST /api/v1/auth/verify-otp/
    Verifies OTP using Email and activates the user account (status: 'pending' -> 'active').
    """
    permission_classes = [] 
    
    def post(self, request, *args, **kwargs):
        serializer = OTPVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        email = serializer.validated_data['email'] # Now uses email
        
        # 1. Account Activation (Critical database write)
        user.status = 'active'
        user.save(update_fields=['status', 'updated_at'])
        
        # 2. Cleanup: Clear OTP from cache immediately after successful use
        cache.delete(f'otp:registration:{email}') # Use email for key

        # 3. Response: Indicate success and next step (KYC)
        return Response({
            "message": "Email verified successfully. Account is now active (status: 'active'). Proceed to secure login and KYC verification to unlock listing features."
        }, status=status.HTTP_200_OK)
    
class CustomTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/v1/auth/token/
    Uses the custom serializer to check user status before issuing a token.
    """
    serializer_class = CustomTokenObtainPairSerializer


# CRITICAL FIX: Simplify the KYCSubmissionAPIView
class KYCSubmissionAPIView(views.APIView): # Change from generics.CreateAPIView to views.APIView
    """
    POST /api/v1/auth/kyc/submit/
    Submits Aadhaar and PAN for verification. Requires JWT authentication.
    """
    serializer_class = KYCSubmissionSerializer # Keep this to retrieve the serializer
    permission_classes = [IsAuthenticated] 

    def post(self, request, *args, **kwargs):
        # 1. Instantiate the serializer with request data
        serializer = KYCSubmissionSerializer(data=request.data, context={'request': request})
        
        # 2. Validate the data (format and uniqueness checks)
        serializer.is_valid(raise_exception=True)
        
        # 3. Perform the custom creation logic (DB writes and status update happen here)
        user = serializer.create(serializer.validated_data)
        
        # 4. Return success response
        return Response({
            "message": "KYC details submitted successfully. Status is now 'pending_kyc'. We will notify you upon verification.",
            "status": user.status 
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
    



