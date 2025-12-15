# apps/listings/urls.py

from django.urls import path
from .views import PropertyListCreateAPIView

urlpatterns = [
    path('', PropertyListCreateAPIView.as_view(), name='property-list-create'),
]