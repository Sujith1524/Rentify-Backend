from rest_framework.throttling import SimpleRateThrottle

class ResendOTPThrottle(SimpleRateThrottle):
    # This 'scope' name is what we will use in settings.py
    scope = 'resend_otp'

    def get_cache_key(self, request, view):
        # We try to rate limit by email first, then fall back to IP address
        email = request.data.get('email')
        if email:
            return f"throttle_{self.scope}_{email}"
        
        # Fallback for 'change' purpose where email isn't in request body
        if request.user.is_authenticated:
            return f"throttle_{self.scope}_{request.user.email}"
            
        return self.get_ident(request) # Standard IP-based throttle