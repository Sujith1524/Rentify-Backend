from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView 
from .views import (
    RegisterAPIView, 
    OTPVerifyAPIView, 
    KYCSubmissionAPIView, 
    UserStatusAPIView,
    LoginOTPRequestAPIView,  
    LoginOTPVerifyAPIView, 
    KYCDraftLoadAPIView,
    KYCDraftSaveAPIView,
    KYCReviewAPIView,
    PasswordResetRequestAPIView,
    PasswordResetConfirmAPIView,
    LogoutAPIView,
    UserProfileAPIView,
    RequestSensitiveChangeAPIView,
    VerifySensitiveChangeAPIView,
    UpdateLocationAPIView,
    ResendOTPAPIView,
)

urlpatterns = [

    # REGISTRATION AUTH FOR USERS
    path('register/', RegisterAPIView.as_view(), name='register'),
    path('verify-otp/', OTPVerifyAPIView.as_view(), name='verify_otp'),
    path('login/request-otp/', LoginOTPRequestAPIView.as_view(), name='login_request_otp'),
    path('login/verify-otp/', LoginOTPVerifyAPIView.as_view(), name='login_verify_otp'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # KYC SUBMISSION
    path('kyc/submit/', KYCSubmissionAPIView.as_view(), name='kyc_submit'),
    path('status/', UserStatusAPIView.as_view(), name='user_status'),

    # LOGIN DRAFT SAVING AND LOADING ENDPOINTS
    path('kyc/save-draft/', KYCDraftSaveAPIView.as_view(), name='kyc-save-draft'),
    path('kyc/load-draft/', KYCDraftLoadAPIView.as_view(), name='kyc-load-draft'),

    # KYC ADMIN APPROVAL ENDPOINT
    path('admin/kyc-review/', KYCReviewAPIView.as_view(), name='admin-kyc-review'),

    # PASSWORD RESET FLOW
    path('password/reset/request/', PasswordResetRequestAPIView.as_view(), name='password-reset-request'),
    path('password/reset/confirm/', PasswordResetConfirmAPIView.as_view(), name='password-reset-confirm'),

    # Explicit Logout (Means the user try to logout the refresh token also get blacklist)
    path('logout/', LogoutAPIView.as_view(), name='logout'), 

    # PROFILE MANAGEMENT [ GET & POST]
    path('profile/', UserProfileAPIView.as_view(), name='user-profile'),

    # PROFILE UPDATION REQUEST OTP SENDING AND VERIFY
    path('profile/sensitive-update-request/', RequestSensitiveChangeAPIView.as_view(), name='sensitive-update-request'),
    path('profile/sensitive-update-verify/', VerifySensitiveChangeAPIView.as_view(), name='sensitive-update-verify'),


    path('profile/location/update/', UpdateLocationAPIView.as_view(), name='location-update'),

    # RESEND OTP REQUESTING ENDPOINT
    path('resend-otp/', ResendOTPAPIView.as_view(), name='resend-otp'),
]
