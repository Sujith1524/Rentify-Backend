import requests
from django.conf import settings

class GeocodingService:
    @staticmethod
    def get_coords_from_address(address):
        """
        Example using OpenStreetMap (Nominatim) - No API Key required for basic testing.
        For production, use Google Maps or Mapbox.
        """
        url = f"https://nominatim.openstreetmap.org/search?q={address}&format=json&limit=1"
        headers = {'User-Agent': 'RentifyApp/1.0'}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            data = response.json()
            if data:
                return {
                    "lat": float(data[0]['lat']),
                    "lng": float(data[0]['lon']),
                    "display_name": data[0]['display_name']
                }
            return None
        except Exception as e:
            print(f"Geocoding error: {e}")
            return None