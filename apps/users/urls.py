from django.urls import path
from .views import (
    RegisterAPIView, 
    OTPVerifyAPIView, 
    KYCSubmissionAPIView, 
    UserStatusAPIView,
    LoginOTPRequestAPIView,  
    LoginOTPVerifyAPIView, 
    KYCDraftLoadAPIView,
    KYCDraftSaveAPIView,
)
from rest_framework_simplejwt.views import TokenRefreshView 

urlpatterns = [

    # Registration Auth
    path('register/', RegisterAPIView.as_view(), name='register'),
    path('verify-otp/', OTPVerifyAPIView.as_view(), name='verify_otp'),
    path('login/request-otp/', LoginOTPRequestAPIView.as_view(), name='login_request_otp'),
    path('login/verify-otp/', LoginOTPVerifyAPIView.as_view(), name='login_verify_otp'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # kyc submission
    path('kyc/submit/', KYCSubmissionAPIView.as_view(), name='kyc_submit'),
    path('status/', UserStatusAPIView.as_view(), name='user_status'),

    # Login Draft Saving and Loading Endpoints
    path('kyc/save-draft/', KYCDraftSaveAPIView.as_view(), name='kyc-save-draft'),
    path('kyc/load-draft/', KYCDraftLoadAPIView.as_view(), name='kyc-load-draft'),
]