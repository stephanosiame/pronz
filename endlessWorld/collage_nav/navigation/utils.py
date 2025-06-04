import os
from twilio.rest import Client
from django.conf import settings
from django.contrib.gis.geos import LineString, Point
import folium
from geopy.distance import geodesic
import random

def send_sms(phone_number, message):
    """Send SMS using Twilio"""
    try:
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            
            message = client.messages.create(
                body=message,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone_number
            )
            return True
        else:
            # In development, print the SMS to console
            print(f"SMS to {phone_number}: {message}")
            return True
    except Exception as e:
        print(f"Error sending SMS: {e}")
        return False

def generate_map_html(center_point, locations=None, route=None):
    """Generate Folium map HTML"""
    # Create map centered at the given point
    m = folium.Map(
        location=[center_point.y, center_point.x],
        zoom_start=17,
        tiles='OpenStreetMap',
        control_scale=True
    )
    
    # Add user location marker
    folium.Marker(
        [center_point.y, center_point.x],
        popup='Your Location',
        icon=folium.Icon(color='blue', icon='user')
    ).add_to(m)
    
    # Add nearby locations
    if locations:
        for location in locations:
            folium.Marker(
                [location.coordinates.y, location.coordinates.x],
                popup=f"<b>{location.name}</b><br>{location.get_location_type_display()}",
                tooltip=location.name,
                icon=folium.Icon(color='green', icon='info-sign')
            ).add_to(m)
    
    # Add route if provided
    if route:
        route_coords = [(point.y, point.x) for point in route.route_path]
        folium.PolyLine(
            route_coords,
            color='red',
            weight=5,
            opacity=0.7,
            tooltip=f"Route: {route.distance:.1f}m"
        ).add_to(m)
    
    # Return HTML representation
    return m._repr_html_()

def calculate_route(from_location, to_location, transport_mode='walking'):
    """Calculate route between two locations"""
    # In a real implementation, you would use a routing service like OSRM, Mapbox, or Google Directions API
    # Here we'll simulate a simple straight-line route
    
    # Create a line between the two points
    route_path = LineString([from_location.coordinates, to_location.coordinates])
    
    # Calculate distance in meters
    distance = geodesic(
        (from_location.coordinates.y, from_location.coordinates.x),
        (to_location.coordinates.y, to_location.coordinates.x)
    ).meters
    
    # Estimate time based on transport mode
    speed_multipliers = {
        'walking': 1.4,    # m/s
        'cycling': 4.2,    # m/s
        'driving': 13.9    # m/s (50 km/h)
    }
    
    speed = speed_multipliers.get(transport_mode, 1.4)
    estimated_time = int(distance / speed / 60)  # in minutes
    duration_seconds = int(distance / speed)     # in seconds
    
    # Create route data structure
    route_data = {
        'source': {
            'id': str(from_location.location_id),
            'name': from_location.name,
            'coordinates': {
                'lat': from_location.coordinates.y,
                'lng': from_location.coordinates.x
            }
        },
        'destination': {
            'id': str(to_location.location_id),
            'name': to_location.name,
            'coordinates': {
                'lat': to_location.coordinates.y,
                'lng': to_location.coordinates.x
            }
        },
        'path': [(from_location.coordinates.y, from_location.coordinates.x),
                (to_location.coordinates.y, to_location.coordinates.x)],
        'distance': distance,
        'estimated_time': estimated_time,
        'duration': estimated_time,  # Added for compatibility
        'steps': [
            {
                'instruction': f"Walk from {from_location.name} to {to_location.name}",
                'distance': distance,
                'duration': duration_seconds  # in seconds
            }
        ]
    }
    
    return route_data

def generate_random_route(from_point, to_point):
    """Generate a random route with intermediate points (for demo purposes)"""
    # This is just for demonstration - in production use a real routing service
    num_points = random.randint(2, 5)
    points = [from_point]
    
    for _ in range(num_points):
        # Create random intermediate points
        lat = from_point.y + (to_point.y - from_point.y) * random.random()
        lng = from_point.x + (to_point.x - from_point.x) * random.random()
        points.append(Point(lng, lat))
    
    points.append(to_point)
    return LineString(points)