# apps/users/tokens.py

from rest_framework_simplejwt.tokens import AccessToken as SimpleJWTAccessToken
from rest_framework_simplejwt.exceptions import TokenError
from datetime import datetime, timezone as dt_timezone

class PasswordUpdateCheckToken(SimpleJWTAccessToken):
    """
    Custom Access Token that invalidates tokens issued before the last
    password update time recorded on the User model.
    """
    
    # We override the verify method which is called during token authentication
    def verify(self):
        super().verify() # Run standard checks (expiry, signature, etc.)

        user_id = self.payload.get('user_id')
        user_model = self.user_class.objects.get(pk=user_id)

        # Get the token's Issue Time (iat)
        token_iat = self.payload.get('iat')
        if not token_iat:
             raise TokenError('Token has no issue time (iat) claim.')
        
        # Convert the token's IAT timestamp (seconds) to a datetime object
        token_issue_time = datetime.fromtimestamp(token_iat, tz=dt_timezone.utc)

        # Get the password update time from the database
        last_update_time = user_model.password_updated_at

        # Rule 5 Enforcement: If the token was issued BEFORE the last password update
        if token_issue_time < last_update_time:
            # This is the security denial: the old session is terminated
            raise TokenError('Password has been updated since this token was issued. Please log in again.')