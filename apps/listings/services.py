from django.db.models import F, ExpressionWrapper, FloatField
from django.db.models.functions import ACos, Cos, Radians, Sin
from .models import Listing

class ListingLocationService:
    @staticmethod
    def get_nearby_listings(user_lat, user_lng, radius_km=50):
        """
        Calculates distance between user coordinates and listing coordinates
        using the Haversine formula directly in PostgreSQL.
        """
        # Ensure coordinates are floats for math operations
        user_lat = float(user_lat)
        user_lng = float(user_lng)

        # Haversine Formula: 6371 is the Earth's radius in KM
        distance_formula = ExpressionWrapper(
            6371 * ACos(
                Cos(Radians(user_lat)) * Cos(Radians(F('latitude'))) *
                Cos(Radians(F('longitude')) - Radians(user_lng)) +
                Sin(Radians(user_lat)) * Sin(Radians(F('latitude')))
            ),
            output_field=FloatField()
        )

        return Listing.objects.annotate(
            distance=distance_formula
        ).filter(
            distance__lte=radius_km
        ).order_by('distance')