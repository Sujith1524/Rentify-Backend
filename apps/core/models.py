import uuid
from django.db import models

class BaseModel(models.Model):
    """Abstract base for all enterprise models."""
    # Ensure the class name is correct (BaseModel, case-sensitive)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True