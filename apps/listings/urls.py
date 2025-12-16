# apps/listings/urls.py

from django.urls import path
from .views import PropertyListCreateAPIView, PropertyRetrieveUpdateDestroyAPIView

urlpatterns = [

    # C/R (List & Create)
    path('', PropertyListCreateAPIView.as_view(), name='property-list-create'),

    # R/U/D (Retrieve, Update, Destroy)
    path('<uuid:pk>/', PropertyRetrieveUpdateDestroyAPIView.as_view(), name='property-rud'),
]