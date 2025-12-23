# apps/users/utils.py

from django.core.cache import cache
import json
import random
import string
import threading
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from .models import PasswordResetOTP
from django.core.mail import send_mail
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

# --- OTP Configuration (Using settings) ---
# Assuming you have SIMPLE_OTP settings in config/settings.py:
# SIMPLE_OTP = {
#     'LENGTH': 6,
#     'TIMEOUT': 300, # 5 minutes in seconds
# }

OTP_LENGTH = getattr(settings, 'SIMPLE_OTP', {}).get('LENGTH', 6)
OTP_TIMEOUT = getattr(settings, 'SIMPLE_OTP', {}).get('TIMEOUT', 300) # 5 minutes

# Load security constants
LOCKOUT_SETTINGS = settings.SECURITY_LOCKOUT

# --- 1. KYC Draft Utilities ---

def get_kyc_draft_key(user_id):
    """Generates the cache key for a user's KYC draft."""
    return f'kyc:draft:{user_id}'

def save_kyc_draft(user_id, data):
    """Saves the partial KYC data (dictionary) to the cache."""
    key = get_kyc_draft_key(user_id)
    
    # Define the timeout as a timedelta object (24 hours)
    draft_timeout = timedelta(hours=24) 
    
    # CRITICAL FIX: Convert the timedelta object to total seconds (an integer/float)
    timeout_seconds = int(draft_timeout.total_seconds()) 
    
    # Store data as a JSON string
    cache.set(key, json.dumps(data), timeout=timeout_seconds)

def load_kyc_draft(user_id):
    """Loads the KYC draft from the cache and returns it as a dictionary."""
    key = get_kyc_draft_key(user_id)
    cached_data = cache.get(key)
    if cached_data:
        return json.loads(cached_data)
    return None

def clear_kyc_draft(user_id):
    """Removes the KYC draft from the cache."""
    key = get_kyc_draft_key(user_id)
    cache.delete(key)

# --- 2. OTP Utilities (New for Login & Password Reset) ---

def get_otp_key(identifier, purpose):
    """Generates the cache key for the OTP."""
    # Identifier is typically the user's email or mobile number
    # Purpose can be 'login', 'registration', or 'reset'
    return f'otp:{purpose}:{identifier}'

def generate_otp_code(length=OTP_LENGTH):
    """Generates a random numeric OTP code."""
    return ''.join(random.choices(string.digits, k=length))


# 1. This class handles the "Background" sending so your API stays fast
class EmailThread(threading.Thread):
    def __init__(self, subject, message, recipient_list):
        self.subject = subject
        self.message = message
        self.recipient_list = recipient_list
        threading.Thread.__init__(self, daemon=True)

    def run(self):
        try:
            send_mail(
                self.subject,
                self.message,
                settings.DEFAULT_FROM_EMAIL,
                self.recipient_list,
                fail_silently=False,
            )
            print(f"📬 [EMAIL-SUCCESS] Sent to {self.recipient_list}")
        except Exception as e:
            print(f"📧 [EMAIL-ERROR] Failed to send: {e}")

def send_password_reset_email(to_email, otp_code):
    subject = "Reset Your Password - Rentify"
    context = {'otp_code': otp_code}
    
    # Render the HTML template with the OTP code
    html_content = render_to_string('emails/password_reset_otp.html', context)
    # Create a plain-text version for email clients that don't support HTML
    text_content = strip_tags(html_content)

    # Create the email object
    msg = EmailMultiAlternatives(
        subject, 
        text_content, 
        settings.DEFAULT_FROM_EMAIL, 
        [to_email]
    )
    msg.attach_alternative(html_content, "text/html")
    
    # Use your thread to send it in the background
    EmailThreadObj(msg).start()

class EmailThreadObj(threading.Thread):
    def __init__(self, email_message):
        self.email_message = email_message
        threading.Thread.__init__(self, daemon=True)

    def run(self):
        try:
            self.email_message.send()
            print(f"📬 [HTML-EMAIL-SUCCESS] Sent to {self.email_message.to}")
        except Exception as e:
            print(f"📧 [EMAIL-ERROR] {e}")


def generate_and_cache_otp(identifier, purpose='reset'):
    clean_email = identifier.lower().strip()
    otp_code = generate_otp_code() 
    
    # Save to Database (Persistent)
    # We only save here. We don't send emails here anymore to avoid duplicates.
    PasswordResetOTP.objects.update_or_create(
        email=clean_email,
        defaults={'otp_code': otp_code, 'created_at': timezone.now()}
    )
    
    # Debugging logs
    print(f"\n--- [DATABASE] OTP SAVED for {purpose.upper()} ---")
    print(f"To: {clean_email} | Code: {otp_code}")
    print(f"---------------------------\n")
    
    return otp_code

def validate_otp(identifier, otp_code, purpose='reset'):
    clean_email = identifier.lower().strip()
    try:
        otp_record = PasswordResetOTP.objects.get(email=clean_email)
        
        # Check code match AND expiration (10 mins)
        if otp_record.otp_code == str(otp_code) and otp_record.is_valid():
            return True
    except PasswordResetOTP.DoesNotExist:
        pass
        
    return False

def clear_otp_from_cache(identifier, purpose='reset'):
    PasswordResetOTP.objects.filter(email=identifier.lower().strip()).delete()


def get_failed_attempts_key(identifier):
    """Generates the cache key for failed attempts."""
    prefix = LOCKOUT_SETTINGS['CACHE_KEY_PREFIX']
    return f"{prefix}{identifier}"

def record_failed_attempt(identifier):
    """
    Records a failed login attempt for the given identifier (email).
    Increments the counter and sets the expiration time.
    """
    key = get_failed_attempts_key(identifier)
    
    # Use cache.incr for atomic increment
    try:
        current_attempts = cache.incr(key)
    except ValueError:
        # If the key doesn't exist, set it to 1 with the full window timeout
        current_attempts = 1
        cache.set(key, current_attempts, timeout=LOCKOUT_SETTINGS['ATTEMPT_WINDOW'])
        
    return current_attempts

def is_account_locked(identifier):
    """
    Checks if the account is currently locked due to too many failed attempts.
    Returns True if locked, False otherwise.
    """
    key = get_failed_attempts_key(identifier)
    current_attempts = cache.get(key, 0) # Default to 0 if key not found
    max_attempts = LOCKOUT_SETTINGS['MAX_ATTEMPTS']
    
    return current_attempts >= max_attempts

def clear_failed_attempts(identifier):
    """Clears the failed attempt count after a successful login."""
    key = get_failed_attempts_key(identifier)
    cache.delete(key)


