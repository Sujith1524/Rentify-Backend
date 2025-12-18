# apps/users/tasks.py
from config.celery import app
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string # Optional for fancy HTML email


def generate_and_cache_otp(user_identifier, purpose='registration'):
    import random
    from django.core.cache import cache
    
    otp_code = str(random.randint(100000, 999999))
    
    key = f'otp:{purpose}:{user_identifier}'
    # Increased timeout to 15 mins (900s) to match your professional templates
    cache.set(key, otp_code, timeout=900) 
    
    # REMOVE OR COMMENT OUT THIS LINE:
    # send_otp_async.delay(user_identifier, otp_code, purpose) 
    
    return otp_code