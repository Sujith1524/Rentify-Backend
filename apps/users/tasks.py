# apps/users/tasks.py
from config.celery import app
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string # Optional for fancy HTML email

@app.task
def send_otp_async(user_identifier, otp_code, purpose):
    """
    Sends OTP via the configured Email backend.
    - user_identifier: The recipient's email address
    - otp_code: The 6-digit code
    """
    subject = f"Rentify: Your {purpose.capitalize()} Verification Code"
    
    # Simple Plain Text Email Body
    message = (
        f"Hi there,\n\n"
        f"Your one-time verification code for Rentify is: {otp_code}\n\n"
        f"This code is valid for 5 minutes.\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"The Rentify Team"
    )

    try:
        # Use Django's send_mail function
        send_mail(
            subject,
            message,
            None, # Uses DEFAULT_FROM_EMAIL from settings
            [user_identifier], # List of recipients (the user's email)
            fail_silently=False,
        )
        print(f"--- SUCCESS: Real Email Sent to {user_identifier} ---")
    except Exception as e:
        # Log error if email fails (e.g., wrong password, port blocked)
        print(f"--- ERROR: Failed to Send Email to {user_identifier}: {e} ---")


# Utility function to generate and cache OTP (This part remains the same)
def generate_and_cache_otp(user_identifier, purpose='registration'):
    # ... (same logic as before) ...
    import random
    
    otp_code = str(random.randint(100000, 999999))
    
    key = f'otp:{purpose}:{user_identifier}'
    cache.set(key, otp_code, timeout=300)
    
    # Dispatch the task to Celery asynchronously
    send_otp_async.delay(user_identifier, otp_code, purpose)
    
    return otp_code