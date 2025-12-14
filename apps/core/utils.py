# apps/core/utils.py

from rest_framework import serializers

def validate_password_complexity(value):
    """
    Enforces enterprise-level password complexity rules.
    Password must:
    1. Be at least 8 characters long.
    2. Contain at least one uppercase letter.
    3. Contain at least one lowercase letter.
    4. Contain at least one digit.
    5. Contain at least one special character.
    """
    if len(value) < 8:
        raise serializers.ValidationError("Password must be at least 8 characters long.")
    if not any(char.isupper() for char in value):
        raise serializers.ValidationError("Password must contain at least one uppercase letter.")
    if not any(char.islower() for char in value):
        raise serializers.ValidationError("Password must contain at least one lowercase letter.")
    if not any(char.isdigit() for char in value):
        # We already added a simple check in the serializer, but this is the refined version
        raise serializers.ValidationError("Password must contain at least one digit.")
    
    special_chars = "!@#$%^&*()_+-=[]{};:\"'<>./?,"
    if not any(char in special_chars for char in value):
        raise serializers.ValidationError("Password must contain at least one special character.")
    
    return value