# apps/listings/urls.py

from django.urls import path
from .views import PropertyListCreateAPIView, PropertyRetrieveUpdateDestroyAPIView, NearbyListingAPIView, PropertyRestoreAPIView

urlpatterns = [
    # C/R (List & Create)
    path('properties/', PropertyListCreateAPIView.as_view(), name='property-list-create'),

    # NEW: Proximity Search (Must be above the UUID path to avoid conflicts)
    path('nearby/', NearbyListingAPIView.as_view(), name='property-nearby'),

    # R/U/D (Retrieve, Update, Soft Delete)
    path('<int:pk>/', PropertyRetrieveUpdateDestroyAPIView.as_view(), name='property-rud'),

    #  Soft Deleted Property Restore
    path('<int:pk>/restore/', PropertyRestoreAPIView.as_view(), name='property-restore'),
]