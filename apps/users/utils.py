# apps/users/utils.py (Add these functions)

from django.core.cache import cache
import json
from datetime import timedelta # Used for checking token expiration

def get_kyc_draft_key(user_id):
    """Generates the cache key for a user's KYC draft."""
    return f'kyc:draft:{user_id}'

def save_kyc_draft(user_id, data):
    """Saves the partial KYC data (dictionary) to the cache."""
    key = get_kyc_draft_key(user_id)
    # Store data as a JSON string
    cache.set(key, json.dumps(data), timeout=timedelta(hours=24)) # Store for 24 hours

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