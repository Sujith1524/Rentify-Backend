# apps/users/utils.py

from django.core.cache import cache
import json
import random
import string
from datetime import timedelta
from django.conf import settings # Needed for OTP settings

# --- OTP Configuration (Using settings) ---
# Assuming you have SIMPLE_OTP settings in config/settings.py:
# SIMPLE_OTP = {
#     'LENGTH': 6,
#     'TIMEOUT': 300, # 5 minutes in seconds
# }

OTP_LENGTH = getattr(settings, 'SIMPLE_OTP', {}).get('LENGTH', 6)
OTP_TIMEOUT = getattr(settings, 'SIMPLE_OTP', {}).get('TIMEOUT', 300) # 5 minutes

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

def generate_and_cache_otp(identifier, purpose):
    """
    Generates an OTP, saves it to cache, and sends it (prints for now).
    Returns the generated OTP code.
    """
    key = get_otp_key(identifier, purpose)
    otp_code = generate_otp_code()
    
    # Cache the OTP with the configured timeout (e.g., 300 seconds)
    cache.set(key, otp_code, timeout=OTP_TIMEOUT)
    
    # TODO: Replace with Celery task to send email
    print(f"\n--- OTP SENT ---")
    print(f"To: {identifier}")
    print(f"Purpose: {purpose}")
    print(f"Code: {otp_code} (Expires in {OTP_TIMEOUT} seconds)")
    print(f"----------------\n")
    
    return otp_code

def validate_otp(identifier, otp_code, purpose):
    """
    Validates the provided OTP code against the cached value.
    Returns True if valid, False otherwise.
    """
    key = get_otp_key(identifier, purpose)
    cached_otp = cache.get(key)
    
    # Validation logic: Must exist and must match
    if cached_otp and cached_otp == otp_code:
        return True
    
    return False

def clear_otp_from_cache(identifier, purpose):
    """Removes the OTP from the cache immediately after successful use."""
    key = get_otp_key(identifier, purpose)
    cache.delete(key)