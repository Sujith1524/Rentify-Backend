from django.urls import path
from .views import RegisterAPIView, OTPVerifyAPIView, KYCSubmissionAPIView, CustomTokenObtainPairView, UserStatusAPIView
from rest_framework_simplejwt.views import TokenRefreshView 

urlpatterns = [
    path('register/', RegisterAPIView.as_view(), name='register'),
    path('verify-otp/', OTPVerifyAPIView.as_view(), name='verify_otp'),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('kyc/submit/', KYCSubmissionAPIView.as_view(), name='kyc_submit'),
    path('status/', UserStatusAPIView.as_view(), name='user_status'),
]